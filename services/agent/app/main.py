import hmac
import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import anthropic
import httpx
from docx import Document
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from pypdf import PdfReader

from app.agents.follow_up.agent import FollowUpError, draft_follow_up
from app.agents.gap_analysis.agent import GapAnalysisError, analyze_gaps
from app.agents.orchestrator import (
    MAX_MISSED_CHECKS,
    ImportResult,
    SearchResult,
    import_companies,
    refresh_boards,
    rescore as orchestrate_rescore,
    run_search as orchestrate_search,
)
from app.agents.schemas import AnthropicKeyRequest, CompanyImport, RunStopped, SearchRule, Usage
from app.auth import CurrentUser, admin_user, current_user
from app.config import Settings, get_settings
from app.crypto import decrypt, encrypt, key_hint
from app.db import Rest, service_db, user_db
from app.mail import alert_admin
from app.sources.base import CompanyNotFound, Posting
from app.telemetry import CallLog, RecordingClient, configure_logging, current_run

logger = logging.getLogger("agent")
configure_logging()

RUN_TIME_LIMIT = timedelta(minutes=10)
UNFINISHED = "in.(queued,running)"
# Days of runs the admin page covers.
STATS_DAYS = 30
# Weeks the admin page's model quality trends cover.
MODEL_WEEKS = 12
# The score that counts as a predicted good fit when scores are checked against ratings.
GOOD_SCORE = 70
# Stop reasons that mean a Claude answer came back cut off or refused.
BROKEN_STOPS = frozenset({"max_tokens", "refusal"})
# A board refresh is refused when another started this recently.
REFRESH_COOLDOWN = timedelta(hours=1)


app = FastAPI(title="job-finder agent")

User = Annotated[CurrentUser, Depends(current_user)]
Admin = Annotated[CurrentUser, Depends(admin_user)]
Config = Annotated[Settings, Depends(get_settings)]


def make_client(api_key: str) -> Any:
    return anthropic.Anthropic(api_key=api_key)


def extract_docx_text(data: bytes) -> str:
    """Paragraphs, then table cells, in document order within each."""
    document = Document(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(line.strip() for line in lines if line.strip())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.put("/me/anthropic-key")
def put_anthropic_key(body: AnthropicKeyRequest, user: User, settings: Config) -> dict[str, str]:
    validate_anthropic_key(body.api_key, settings)
    hint = key_hint(body.api_key)
    service_db(settings).insert(
        "api_credentials",
        {"user_id": user.id, "provider": "anthropic", "ciphertext": encrypt(body.api_key, settings.agent_encryption_key)},
        on_conflict="user_id,provider",
    )
    user_db(settings, user.access_token).insert(
        "profiles", {"user_id": user.id, "anthropic_key_hint": hint}, on_conflict="user_id"
    )
    return {"hint": hint}


@app.delete("/me/anthropic-key", status_code=204)
def delete_anthropic_key(user: User, settings: Config) -> None:
    service_db(settings).delete("api_credentials", {"user_id": f"eq.{user.id}", "provider": "eq.anthropic"})
    user_db(settings, user.access_token).insert(
        "profiles", {"user_id": user.id, "anthropic_key_hint": None}, on_conflict="user_id"
    )


@app.post("/resumes/{resume_id}/extract")
def extract_resume(resume_id: str, user: User, settings: Config) -> dict[str, Any]:
    db = user_db(settings, user.access_token)
    rows = db.select("resumes", {"id": f"eq.{resume_id}", "select": "id,storage_path,file_name"})
    if not rows:
        raise HTTPException(404, "Resume not found.")
    resume = rows[0]
    file_name = resume["file_name"].lower()
    if file_name.endswith(".docx"):
        extract = extract_docx_text
    elif file_name.endswith(".pdf"):
        extract = extract_pdf_text
    else:
        raise HTTPException(400, "Only PDF and .docx resumes are supported.")

    text = extract(db.download("resumes", resume["storage_path"]))
    if not text:
        raise HTTPException(422, "No text found in this file. Scanned PDFs aren't supported.")
    db.update("resumes", {"id": f"eq.{resume_id}"}, {"text": text})
    return {"id": resume_id, "characters": len(text)}


@app.post("/runs/search", status_code=202)
def start_search(body: SearchRule, user: User, settings: Config, background: BackgroundTasks) -> dict[str, str]:
    db = user_db(settings, user.access_token)
    cutoff = (datetime.now(UTC) - RUN_TIME_LIMIT).isoformat()
    fail_runs(db, {"status": UNFINISHED, "created_at": f"lt.{cutoff}"}, "Stopped after running for more than 10 minutes.")
    try:
        run = db.insert("agent_runs", {"user_id": user.id, "kind": "search", "input": body.model_dump()})[0]
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            raise HTTPException(409, "A search is already running. Wait for it to finish.")
        raise
    background.add_task(run_search, run["id"], body, user, settings)
    return {"run_id": run["id"]}


def run_search(run_id: str, body: SearchRule, user: CurrentUser, settings: Settings) -> None:
    db = user_db(settings, user.access_token)
    service = service_db(settings)
    usage = Usage()
    report = start_run(db, run_id)
    calls, timings = CallLog(user.id, run_id), {}
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Searches aren't set up yet: the app has no Anthropic key. Ask the admin to add one.")

        resume = None
        if body.score:
            resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
            if not resumes or not resumes[0]["text"]:
                raise RuntimeError("Upload a resume first, or search without scoring.")
            resume = resumes[0]

        result = orchestrate_search(
            rule=body,
            client=RecordingClient(make_client(api_key), calls),
            settings=settings,
            resume_id=resume["id"] if resume else None,
            resume_text=resume["text"] if resume else None,
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
            timings=timings,
        )
        outcome = {
            "status": "done",
            "error": None,
            "error_code": None,
            "progress": summarize(result),
            "jobs_added": result.kept,
            "unreachable_boards": result.unreachable_boards,
            "board_fetches": result.board_fetches,
        }
    except RunStopped:
        pass
    except CompanyNotFound as exc:
        outcome = {"status": "failed", "error": str(exc), "error_code": "company_not_found", "progress": None}
    except Exception as exc:
        logger.exception("search run %s failed", run_id)
        outcome = {"status": "failed", "error": str(exc) or exc.__class__.__name__, "error_code": None, "progress": None}

    finish_run(db, run_id, outcome, usage, timings)
    calls.save(service)


def extract_pdf_text(data: bytes) -> str:
    """Text of every page in order; empty for scanned PDFs with no text layer."""
    pages = (page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    lines = "\n".join(pages).splitlines()
    return "\n".join(line.strip() for line in lines if line.strip())


def summarize(result: SearchResult) -> str:
    """Final one-line progress for a finished search."""
    if result.company and result.found == 0:
        return f"Found {result.company}, but it has no open jobs listed."
    if result.matched == 0:
        return "No jobs match your search."
    if result.kept == 0:
        if result.scored and result.min_score:
            return f"No new jobs scored {result.min_score} or higher."
        if result.failed:
            return "Couldn't score the matching jobs. Try again."
        return "No new jobs: every match is already on your list."
    jobs = "job" if result.kept == 1 else "jobs"
    if result.scored == 0:
        return f"Added the {result.kept} newest {jobs}."
    if result.min_score:
        return f"Added {result.kept} {jobs} scoring {result.min_score} or higher."
    if result.kept < result.scored:
        return f"Added your {result.kept} best-matching {jobs}."
    return f"Added {result.kept} {jobs}."


def fail_runs(db: Rest, filters: dict[str, str], error: str) -> None:
    """Marks matching unfinished runs as failed with error code timed_out, so they stop showing as running."""
    db.update(
        "agent_runs",
        filters,
        {
            "status": "failed",
            "error": error,
            "error_code": "timed_out",
            "progress": None,
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )


@app.post("/runs/rescore", status_code=202)
def start_rescore(user: User, settings: Config, background: BackgroundTasks) -> dict[str, str]:
    db = user_db(settings, user.access_token)
    cutoff = (datetime.now(UTC) - RUN_TIME_LIMIT).isoformat()
    fail_runs(db, {"status": UNFINISHED, "created_at": f"lt.{cutoff}"}, "Stopped after running for more than 10 minutes.")
    try:
        run = db.insert("agent_runs", {"user_id": user.id, "kind": "rescore", "input": {}})[0]
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            raise HTTPException(409, "A search is already running. Wait for it to finish.")
        raise
    background.add_task(run_rescore, run["id"], user, settings)
    return {"run_id": run["id"]}


def run_rescore(run_id: str, user: CurrentUser, settings: Settings) -> None:
    db = user_db(settings, user.access_token)
    service = service_db(settings)
    usage = Usage()
    report = start_run(db, run_id)
    calls, timings = CallLog(user.id, run_id), {}
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Searches aren't set up yet: the app has no Anthropic key. Ask the admin to add one.")

        resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
        if not resumes or not resumes[0]["text"]:
            raise RuntimeError("Upload a resume first.")

        count = orchestrate_rescore(
            client=RecordingClient(make_client(api_key), calls),
            settings=settings,
            resume_id=resumes[0]["id"],
            resume_text=resumes[0]["text"],
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
            timings=timings,
        )
        progress = (
            f"Scored {count} {'job' if count == 1 else 'jobs'} with your current resume."
            if count
            else "Every job is already scored with your current resume."
        )
        outcome = {"status": "done", "error": None, "progress": progress}
    except RunStopped:
        pass
    except Exception as exc:
        logger.exception("rescore run %s failed", run_id)
        outcome = {"status": "failed", "error": str(exc) or exc.__class__.__name__, "progress": None}

    finish_run(db, run_id, outcome, usage, timings)
    calls.save(service)


@app.post("/runs/import", status_code=202)
def start_import(body: CompanyImport, user: User, settings: Config, background: BackgroundTasks) -> dict[str, str]:
    db = user_db(settings, user.access_token)
    cutoff = (datetime.now(UTC) - RUN_TIME_LIMIT).isoformat()
    fail_runs(db, {"status": UNFINISHED, "created_at": f"lt.{cutoff}"}, "Stopped after running for more than 10 minutes.")
    try:
        run = db.insert("agent_runs", {"user_id": user.id, "kind": "import", "input": body.model_dump()})[0]
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            raise HTTPException(409, "A search is already running. Wait for it to finish.")
        raise
    background.add_task(run_import, run["id"], body, user, settings)
    return {"run_id": run["id"]}


def run_import(run_id: str, body: CompanyImport, user: CurrentUser, settings: Settings) -> None:
    db = user_db(settings, user.access_token)
    service = service_db(settings)
    usage = Usage()
    report = start_run(db, run_id)
    calls, timings = CallLog(user.id, run_id), {}
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Searches aren't set up yet: the app has no Anthropic key. Ask the admin to add one.")

        result = import_companies(
            entries=body.entries,
            client=RecordingClient(make_client(api_key), calls),
            settings=settings,
            service=service,
            usage=usage,
            report=report,
        )
        outcome = {"status": "done", "error": None, "progress": summarize_import(result)}
    except RunStopped:
        pass
    except Exception as exc:
        logger.exception("import run %s failed", run_id)
        outcome = {"status": "failed", "error": str(exc) or exc.__class__.__name__, "progress": None}

    finish_run(db, run_id, outcome, usage, timings)
    calls.save(service)


def summarize_import(result: ImportResult) -> str:
    """Final one-line progress for a finished import."""
    parts = [f"Added {len(result.added)} {'company' if len(result.added) == 1 else 'companies'}"]
    if result.empty:
        parts.append(f"{', '.join(result.empty)} {'has' if len(result.empty) == 1 else 'have'} no open jobs listed")
    if result.existing:
        parts.append(f"{result.existing} already in the directory")
    if result.not_found:
        parts.append(f"couldn't find {', '.join(result.not_found)}")
    return ", ".join(parts) + "."


def claude_and_resume(user: CurrentUser, settings: Settings) -> tuple[Any, str, CallLog]:
    """
    The user's recording Claude client, primary resume text and the log its
    calls go to, or a 400 saying which one is missing.
    """
    api_key = anthropic_key(service_db(settings), user.id, settings)
    if not api_key:
        raise HTTPException(400, "This isn't set up yet: the app has no Anthropic key. Ask the admin to add one.")
    resumes = user_db(settings, user.access_token).select("resumes", {"is_primary": "eq.true", "select": "text"})
    if not resumes or not resumes[0]["text"]:
        raise HTTPException(400, "Upload a resume first.")
    calls = CallLog(user.id)
    return RecordingClient(make_client(api_key), calls), resumes[0]["text"], calls


@app.post("/applications/{application_id}/gap-analysis")
def post_gap_analysis(application_id: str, user: User, settings: Config) -> dict[str, Any]:
    db = user_db(settings, user.access_token)
    rows = db.select("applications", {"id": f"eq.{application_id}", "select": "id,posting:postings(*)"})
    if not rows:
        raise HTTPException(404, "Job not found.")
    client, resume_text, calls = claude_and_resume(user, settings)
    usage = Usage()
    try:
        analysis = analyze_gaps(client, settings.analysis_model, resume_text, Posting.model_validate(rows[0]["posting"]), usage)
    except (GapAnalysisError, anthropic.APIError) as error:
        raise HTTPException(502, f"Couldn't analyze this job: {error}")
    finally:
        calls.save(service_db(settings))
    db.update(
        "applications",
        {"id": f"eq.{application_id}"},
        {"gap_analysis": analysis.model_dump(), "gap_analyzed_at": datetime.now(UTC).isoformat()},
    )
    return {"gap_analysis": analysis.model_dump(), "usage": usage.model_dump()}


@app.post("/applications/{application_id}/follow-up")
def post_follow_up(application_id: str, user: User, settings: Config) -> dict[str, Any]:
    db = user_db(settings, user.access_token)
    rows = db.select(
        "applications",
        {
            "id": f"eq.{application_id}",
            "select": "id,posting:postings(title,company),events:application_events(status,changed_at)",
        },
    )
    if not rows:
        raise HTTPException(404, "Job not found.")
    applied = sorted(event["changed_at"] for event in rows[0]["events"] if event["status"] == "applied")
    if not applied:
        raise HTTPException(400, "This job was never marked applied.")
    client, resume_text, calls = claude_and_resume(user, settings)
    usage = Usage()
    posting = rows[0]["posting"]
    try:
        draft = draft_follow_up(
            client, settings.analysis_model, resume_text, posting["title"], posting["company"], applied[-1][:10], usage
        )
    except (FollowUpError, anthropic.APIError) as error:
        raise HTTPException(502, f"Couldn't draft a follow-up: {error}")
    finally:
        calls.save(service_db(settings))
    return {**draft.model_dump(), "usage": usage.model_dump()}


def anthropic_key(service: Rest, user_id: str, settings: Settings) -> str | None:
    """
    The user's saved Anthropic key, else the shared key an admin saved, else
    the ANTHROPIC_API_KEY setting, else None.
    """
    credentials = service.select(
        "api_credentials", {"user_id": f"eq.{user_id}", "provider": "eq.anthropic", "select": "ciphertext"}
    )
    if not credentials:
        credentials = service.select("shared_credentials", {"provider": "eq.anthropic", "select": "ciphertext"})
    if credentials:
        return decrypt(credentials[0]["ciphertext"], settings.agent_encryption_key)
    return settings.anthropic_api_key


def start_run(db: Rest, run_id: str) -> Callable[[str], None]:
    """
    Marks a queued run running and returns its progress reporter. Progress is
    written only while the run is still running; once the user has stopped it,
    the next report raises RunStopped. Logs from here on carry the run's id.
    """
    current_run.set(run_id)
    logger.info("run started")
    db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.queued"}, {"status": "running", "progress": "Starting…"})

    def report(message: str) -> None:
        if not db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running"}, {"progress": message}):
            raise RunStopped()

    return report


def finish_run(db: Rest, run_id: str, outcome: dict[str, Any], usage: Usage, timings: dict[str, int]) -> None:
    """
    Saves a run's outcome while it's still running; a run the user stopped keeps
    its status and gets only its usage and step timings.
    """
    measured = {"usage": usage.model_dump(), "timings": timings or None}
    logger.info(
        "run finished",
        extra={"status": outcome.get("status", "stopped"), "timings": timings, "input_tokens": usage.input_tokens},
    )
    finished = {**measured, "finished_at": datetime.now(UTC).isoformat()}
    if outcome and db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running"}, {**outcome, **finished}):
        return
    db.update("agent_runs", {"id": f"eq.{run_id}"}, measured)


@app.post("/runs/{run_id}/stop")
def stop_run(run_id: str, user: User, settings: Config) -> dict[str, str]:
    """Stops a queued or running run; its background task halts at its next progress update."""
    db = user_db(settings, user.access_token)
    stopped = db.update(
        "agent_runs",
        {"id": f"eq.{run_id}", "status": UNFINISHED},
        {"status": "stopped", "progress": "Stopped.", "finished_at": datetime.now(UTC).isoformat()},
    )
    if not stopped:
        raise HTTPException(409, "This search already finished.")
    return {"status": "stopped"}


def validate_anthropic_key(api_key: str, settings: Settings) -> None:
    """Raises a 400 or 502 unless Anthropic accepts the key for the scoring model."""
    try:
        make_client(api_key).models.retrieve(settings.scoring_model)
    except anthropic.AuthenticationError:
        raise HTTPException(400, "Anthropic rejected this key.")
    except anthropic.PermissionDeniedError:
        raise HTTPException(400, f"This key can't use {settings.scoring_model}.")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach Anthropic to validate the key.")


@app.get("/admin/anthropic-key")
def get_shared_key(admin: Admin, settings: Config) -> dict[str, Any]:
    """The shared key's last four characters, and whether ANTHROPIC_API_KEY backs it up."""
    rows = service_db(settings).select("shared_credentials", {"provider": "eq.anthropic", "select": "hint"})
    return {"hint": rows[0]["hint"] if rows else None, "fallback": bool(settings.anthropic_api_key)}


@app.put("/admin/anthropic-key")
def put_shared_key(body: AnthropicKeyRequest, admin: Admin, settings: Config) -> dict[str, str]:
    """Validates and saves the shared key runs use when a user has no key of their own."""
    validate_anthropic_key(body.api_key, settings)
    hint = key_hint(body.api_key)
    service_db(settings).insert(
        "shared_credentials",
        {"provider": "anthropic", "ciphertext": encrypt(body.api_key, settings.agent_encryption_key), "hint": hint},
        on_conflict="provider",
    )
    return {"hint": hint}


@app.delete("/admin/anthropic-key", status_code=204)
def delete_shared_key(admin: Admin, settings: Config) -> None:
    service_db(settings).delete("shared_credentials", {"provider": "eq.anthropic"})


@app.get("/admin/stats")
def admin_stats(admin: Admin, settings: Config) -> dict[str, Any]:
    """
    App-wide data for the admin page: every user, the last STATS_DAYS of runs,
    of Claude calls summed up by step, of board fetches by board and job system
    and of page load measurements by page,
    the last MODEL_WEEKS of model quality by week and by prompt version, the
    latest evaluation runs, the board refreshes with each board's fetch times and storage,
    the company directory, every good or bad label, and jobs past "new".
    """
    service = service_db(settings)
    since = (datetime.now(UTC) - timedelta(days=STATS_DAYS)).isoformat()
    model_since = (datetime.now(UTC) - timedelta(weeks=MODEL_WEEKS)).isoformat()
    model_calls = select_all(
        service,
        "llm_calls",
        {
            "select": "step,model,prompt_version,stop_reason,error,duration_ms,input_tokens,cache_read_input_tokens,created_at",
            "created_at": f"gte.{model_since}",
            "order": "id",
        },
    )
    scores = select_all(
        service,
        "applications",
        {
            "select": "fit_score,fit_label,score_model,score_prompt_version,created_at,updated_at",
            "fit_score": "not.is.null",
            "created_at": f"gte.{model_since}",
            "order": "id",
        },
    )
    searches = service.select(
        "agent_runs",
        {"select": "usage,created_at", "kind": "eq.search", "status": "eq.done", "created_at": f"gte.{model_since}"},
    )
    refreshes = service.select(
        "board_refreshes",
        {
            "select": "id,started_at,finished_at,boards,jobs,new_jobs,closed_jobs,embedded_jobs,deleted_jobs,failures,board_fetches",
            "started_at": f"gte.{since}",
            "order": "started_at.desc",
        },
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "days": STATS_DAYS,
        "max_missed_checks": MAX_MISSED_CHECKS,
        "users": [
            {
                "id": user["id"],
                "email": user.get("email"),
                "created_at": user.get("created_at"),
                "last_sign_in_at": user.get("last_sign_in_at"),
            }
            for user in service.list_users()
        ],
        "runs": service.select(
            "agent_runs",
            {
                "select": "id,user_id,kind,status,error,error_code,unreachable_boards,created_at,finished_at,usage,timings",
                "created_at": f"gte.{since}",
                "order": "created_at.desc",
            },
        ),
        "calls": call_stats(
            select_all(
                service,
                "llm_calls",
                {
                    "select": "step,duration_ms,error,input_tokens,output_tokens,cache_read_input_tokens,"
                    "cache_creation_input_tokens,web_search_requests",
                    "created_at": f"gte.{since}",
                    "order": "id",
                },
            )
        ),
        "vitals": vital_stats(
            select_all(
                service,
                "web_vitals",
                {"select": "page,metric,value", "created_at": f"gte.{since}", "order": "id"},
            )
        ),
        "boards": board_stats(
            [
                fetch
                for run in service.select(
                    "agent_runs", {"select": "board_fetches", "kind": "eq.search", "created_at": f"gte.{since}"}
                )
                for fetch in run["board_fetches"] or []
            ]
        ),
        "model_weeks": model_weeks(model_calls, scores, searches),
        "prompt_versions": prompt_versions(model_calls),
        "score_versions": score_versions(scores),
        "evals": service.select(
            "eval_runs",
            {"select": "eval,model,prompt_version,metrics,cost,created_at", "order": "created_at.desc", "limit": "20"},
        ),
        "refreshes": refreshes,
        "refresh_boards": refresh_board_rows(refreshes, service.rpc("board_storage", {})),
        "companies": service.select("companies", {"select": "name,source,board,kind,open_jobs,missed_checks"}),
        "labels": service.select("applications", {"select": "fit_score,fit_label", "fit_label": "not.is.null"}),
        "applications": service.select("applications", {"select": "user_id,status", "status": "neq.new"}),
    }


def select_all(service: Rest, table: str, params: dict[str, str], page: int = 1000) -> list[dict[str, Any]]:
    """Every matching row, fetched a page at a time past the API's row limit; params need a stable order."""
    rows: list[dict[str, Any]] = []
    while True:
        batch = service.select(table, {**params, "limit": str(page), "offset": str(len(rows))})
        rows += batch
        if len(batch) < page:
            return rows


def call_stats(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Claude calls summed up by step: count, errors, median and slowest-5% time, and token totals; busiest first."""
    by_step: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_step.setdefault(call["step"], []).append(call)
    stats = []
    for step, rows in by_step.items():
        times = sorted(row["duration_ms"] for row in rows)
        stats.append(
            {
                "step": step,
                "calls": len(rows),
                "errors": sum(1 for row in rows if row["error"]),
                "median_ms": times[len(times) // 2],
                "p95_ms": times[min(len(times) - 1, int(len(times) * 0.95))],
                **{
                    field: sum(row[field] for row in rows)
                    for field in (
                        "input_tokens",
                        "output_tokens",
                        "cache_read_input_tokens",
                        "cache_creation_input_tokens",
                        "web_search_requests",
                    )
                },
            }
        )
    return sorted(stats, key=lambda row: row["calls"], reverse=True)


def vital_stats(vitals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Page speed measurements by page title and metric: count, median and 75th percentile; most measured pages first."""
    groups: dict[tuple[str, str], list[float]] = {}
    for row in vitals:
        groups.setdefault((row["page"], row["metric"]), []).append(row["value"])
    stats = []
    for (page, metric), values in groups.items():
        values.sort()
        stats.append(
            {
                "page": page,
                "metric": metric,
                "count": len(values),
                "median": values[len(values) // 2],
                "p75": values[min(len(values) - 1, int(len(values) * 0.75))],
            }
        )
    loads: dict[str, int] = {}
    for row in stats:
        loads[row["page"]] = max(loads.get(row["page"], 0), row["count"])
    return sorted(stats, key=lambda row: (-loads[row["page"]], row["page"], row["metric"]))


# Boards listed on the admin page, slowest first.
SLOW_BOARDS = 15


def board_stats(fetches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Board fetches summed up per job system (fetches, failures, median and
    slowest time, jobs) and the SLOW_BOARDS slowest boards by median time.
    """

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        times = sorted(row["ms"] for row in rows)
        return {
            "fetches": len(rows),
            "failures": sum(1 for row in rows if row["outcome"] not in ("ok", "cached")),
            "cached": sum(1 for row in rows if row["outcome"] == "cached"),
            "median_ms": times[len(times) // 2],
            "max_ms": times[-1],
            "jobs": max(row["jobs"] for row in rows),
        }

    by_source: dict[str, list[dict[str, Any]]] = {}
    by_board: dict[str, list[dict[str, Any]]] = {}
    for fetch in fetches:
        by_source.setdefault(fetch["source"], []).append(fetch)
        by_board.setdefault(fetch["board"], []).append(fetch)
    sources = [
        {"source": source, **summarize(rows), "total_ms": sum(row["ms"] for row in rows)} for source, rows in by_source.items()
    ]
    boards = [{"board": board, "source": rows[0]["source"], **summarize(rows)} for board, rows in by_board.items()]
    return {
        "sources": sorted(sources, key=lambda row: row["total_ms"], reverse=True),
        "slowest": sorted(boards, key=lambda row: row["median_ms"], reverse=True)[:SLOW_BOARDS],
    }


def refresh_board_rows(refreshes: list[dict[str, Any]], storage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Each board's refresh fetches, newest refresh first, summed up with its saved
    jobs and their storage: median and latest fetch time, failed fetches, open,
    embedded and saved jobs, and bytes. Slowest median first.
    """
    fetches: dict[str, list[dict[str, Any]]] = {}
    for refresh in refreshes:
        for fetch in refresh["board_fetches"]:
            fetches.setdefault(fetch["board"], []).append(fetch)
    stored = {f"{row['source']}/{row['board']}": row for row in storage}
    rows = []
    for board in fetches.keys() | stored.keys():
        runs = fetches.get(board, [])
        times = sorted(run["ms"] for run in runs)
        saved = stored.get(board, {})
        rows.append(
            {
                "board": board,
                "source": board.split("/", 1)[0],
                "median_ms": times[len(times) // 2] if times else None,
                "last_ms": runs[0]["ms"] if runs else None,
                "last_outcome": runs[0]["outcome"] if runs else None,
                "failures": sum(1 for run in runs if run["outcome"] != "ok"),
                "open_jobs": saved.get("open_jobs", 0),
                "embedded": saved.get("embedded", 0),
                "saved_jobs": saved.get("jobs", 0),
                "bytes": saved.get("bytes", 0),
            }
        )
    return sorted(rows, key=lambda row: row["median_ms"] or -1, reverse=True)


@app.post("/refresh", status_code=202)
def start_refresh(settings: Config, background: BackgroundTasks, authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    """Starts the daily board refresh; the caller sends the cron secret, and a refresh within REFRESH_COOLDOWN is refused."""
    if not settings.cron_secret:
        raise HTTPException(status_code=503, detail="Board refresh isn't set up: CRON_SECRET is missing.")
    if not hmac.compare_digest((authorization or "").encode(), f"Bearer {settings.cron_secret}".encode()):
        raise HTTPException(status_code=401, detail="Not allowed.")
    since = (datetime.now(UTC) - REFRESH_COOLDOWN).isoformat()
    if service_db(settings).select("board_refreshes", {"select": "id", "started_at": f"gte.{since}", "limit": "1"}):
        raise HTTPException(status_code=409, detail="A board refresh started less than an hour ago.")
    background.add_task(run_refresh, settings)
    return {"status": "started"}


def run_refresh(settings: Settings) -> None:
    """Runs the board refresh and emails the admin when it fails or can't reach some boards, at most once a day each."""
    today = datetime.now(UTC).date().isoformat()
    try:
        summary = refresh_boards(service_db(settings))
    except Exception as error:
        logger.exception("board refresh failed")
        alert_admin(
            settings,
            "Board refresh failed",
            [f"The daily board refresh stopped with an error: {error}", "Searches fetch boards live until the next refresh succeeds."],
            f"refresh-failed/{today}",
        )
        return
    logger.info("board refresh finished", extra={key: value for key, value in summary.items() if key != "board_fetches"})
    unreachable = sorted(fetch["board"] for fetch in summary["board_fetches"] if fetch["outcome"] == "unreachable")
    if unreachable:
        alert_admin(
            settings,
            f"Board refresh couldn't reach {len(unreachable)} {'board' if len(unreachable) == 1 else 'boards'}",
            [
                f"The refresh saved {summary['jobs']:,} jobs from {summary['boards']} boards, but these failed twice in a row:",
                *unreachable,
                "Searches fetch these boards live; if they keep failing, check them on the admin page.",
            ],
            f"refresh-unreachable/{today}",
        )


def week_of(timestamp: str) -> str:
    """The Monday that starts the week of an ISO timestamp, as "2026-11-09"."""
    day = datetime.fromisoformat(timestamp).date()
    return (day - timedelta(days=day.weekday())).isoformat()


def model_weeks(
    calls: list[dict[str, Any]], scores: list[dict[str, Any]], searches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Per week, oldest first: Claude calls with their errors, cut-off or refused
    answers, median time and cache share; finished searches with their summed
    usage; and fit scores given and ratings made, for spotting drift.
    """
    weeks: dict[str, dict[str, Any]] = {}

    def week(timestamp: str) -> dict[str, Any]:
        return weeks.setdefault(
            week_of(timestamp),
            {"times": [], "calls": 0, "errors": 0, "broken": 0, "input": 0, "cached": 0, "searches": 0,
             "usage": {}, "scored": 0, "score_total": 0, "rated": 0, "good": 0},
        )

    for call in calls:
        row = week(call["created_at"])
        row["calls"] += 1
        row["errors"] += bool(call["error"])
        row["broken"] += call["stop_reason"] in BROKEN_STOPS
        row["times"].append(call["duration_ms"])
        row["input"] += call["input_tokens"] + call["cache_read_input_tokens"]
        row["cached"] += call["cache_read_input_tokens"]
    for search in searches:
        row = week(search["created_at"])
        row["searches"] += 1
        for field, value in (search["usage"] or {}).items():
            row["usage"][field] = row["usage"].get(field, 0) + (value or 0)
    for score in scores:
        row = week(score["created_at"])
        row["scored"] += 1
        row["score_total"] += score["fit_score"]
        if score["fit_label"]:
            rated = week(score["updated_at"])
            rated["rated"] += 1
            rated["good"] += score["fit_label"] == "good"
    return [
        {
            "week": key,
            "calls": row["calls"],
            "errors": row["errors"],
            "broken": row["broken"],
            "median_ms": sorted(row["times"])[len(row["times"]) // 2] if row["times"] else None,
            "cache_share": row["cached"] / row["input"] if row["input"] else None,
            "searches": row["searches"],
            "search_usage": row["usage"],
            "scored": row["scored"],
            "average_score": row["score_total"] / row["scored"] if row["scored"] else None,
            "rated": row["rated"],
            "good": row["good"],
        }
        for key, row in sorted(weeks.items())
    ]


def prompt_versions(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each step's prompt versions and models with their calls and when they were first and last used; newest first."""
    groups: dict[tuple[str, str | None, str], list[str]] = {}
    for call in calls:
        groups.setdefault((call["step"], call["prompt_version"], call["model"]), []).append(call["created_at"])
    rows = [
        {"step": step, "prompt_version": version, "model": model, "calls": len(times), "first": min(times), "last": max(times)}
        for (step, version, model), times in groups.items()
    ]
    return sorted(rows, key=lambda row: (row["step"], row["last"]), reverse=True)


def score_versions(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fit scores by the prompt version and model that gave them: how many, their
    average, how many were rated, how many of those good, and how many of the
    rated jobs scoring GOOD_SCORE or more were rated good. Newest first.
    """
    groups: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for score in scores:
        groups.setdefault((score["score_prompt_version"], score["score_model"]), []).append(score)
    rows = []
    for (version, model), group in groups.items():
        rated = [row for row in group if row["fit_label"]]
        predicted = [row for row in rated if row["fit_score"] >= GOOD_SCORE]
        rows.append(
            {
                "prompt_version": version,
                "model": model,
                "scored": len(group),
                "average_score": sum(row["fit_score"] for row in group) / len(group),
                "rated": len(rated),
                "good": sum(row["fit_label"] == "good" for row in rated),
                "predicted_good": len(predicted),
                "predicted_good_correct": sum(row["fit_label"] == "good" for row in predicted),
                "last": max(row["created_at"] for row in group),
            }
        )
    return sorted(rows, key=lambda row: row["last"], reverse=True)
