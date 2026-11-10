import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import anthropic
import httpx
from docx import Document
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pypdf import PdfReader

from app.agents.orchestrator import (
    ImportResult,
    SearchResult,
    import_companies,
    rescore as orchestrate_rescore,
    run_search as orchestrate_search,
)
from app.agents.follow_up.agent import FollowUpError, draft_follow_up
from app.agents.gap_analysis.agent import GapAnalysisError, analyze_gaps
from app.agents.schemas import AnthropicKeyRequest, CompanyImport, RunStopped, SearchRule, Usage
from app.auth import CurrentUser, admin_user, current_user
from app.config import Settings, get_settings
from app.crypto import decrypt, encrypt, key_hint
from app.db import Rest, service_db, user_db
from app.sources.base import CompanyNotFound, Posting

logger = logging.getLogger("agent")

RUN_TIME_LIMIT = timedelta(minutes=10)
UNFINISHED = "in.(queued,running)"
# Days of runs the admin page covers.
STATS_DAYS = 30


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
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        resume = None
        if body.score:
            resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
            if not resumes or not resumes[0]["text"]:
                raise RuntimeError("Upload a resume first, or search without scoring.")
            resume = resumes[0]

        result = orchestrate_search(
            rule=body,
            client=make_client(api_key),
            settings=settings,
            resume_id=resume["id"] if resume else None,
            resume_text=resume["text"] if resume else None,
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
        )
        outcome = {"status": "done", "error": None, "error_code": None, "progress": summarize(result)}
    except RunStopped:
        pass
    except CompanyNotFound as exc:
        outcome = {"status": "failed", "error": str(exc), "error_code": "company_not_found", "progress": None}
    except Exception as exc:
        logger.exception("search run %s failed", run_id)
        outcome = {"status": "failed", "error": str(exc) or exc.__class__.__name__, "error_code": None, "progress": None}

    finish_run(db, run_id, outcome, usage)


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
    """Marks matching unfinished runs as failed so they stop showing as running."""
    db.update(
        "agent_runs",
        filters,
        {"status": "failed", "error": error, "progress": None, "finished_at": datetime.now(UTC).isoformat()},
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
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
        if not resumes or not resumes[0]["text"]:
            raise RuntimeError("Upload a resume first.")

        count = orchestrate_rescore(
            client=make_client(api_key),
            settings=settings,
            resume_id=resumes[0]["id"],
            resume_text=resumes[0]["text"],
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
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

    finish_run(db, run_id, outcome, usage)


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
    outcome: dict[str, Any] = {}
    try:
        api_key = anthropic_key(service, user.id, settings)
        if not api_key:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        result = import_companies(
            entries=body.entries,
            client=make_client(api_key),
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

    finish_run(db, run_id, outcome, usage)


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


def claude_and_resume(user: CurrentUser, settings: Settings) -> tuple[Any, str]:
    """The user's Claude client and primary resume text, or a 400 saying which one is missing."""
    api_key = anthropic_key(service_db(settings), user.id, settings)
    if not api_key:
        raise HTTPException(400, "Add your Anthropic API key in Settings first.")
    resumes = user_db(settings, user.access_token).select("resumes", {"is_primary": "eq.true", "select": "text"})
    if not resumes or not resumes[0]["text"]:
        raise HTTPException(400, "Upload a resume first.")
    return make_client(api_key), resumes[0]["text"]


@app.post("/applications/{application_id}/gap-analysis")
def post_gap_analysis(application_id: str, user: User, settings: Config) -> dict[str, Any]:
    db = user_db(settings, user.access_token)
    rows = db.select("applications", {"id": f"eq.{application_id}", "select": "id,posting:postings(*)"})
    if not rows:
        raise HTTPException(404, "Job not found.")
    client, resume_text = claude_and_resume(user, settings)
    usage = Usage()
    try:
        analysis = analyze_gaps(client, settings.analysis_model, resume_text, Posting.model_validate(rows[0]["posting"]), usage)
    except (GapAnalysisError, anthropic.APIError) as error:
        raise HTTPException(502, f"Couldn't analyze this job: {error}")
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
    client, resume_text = claude_and_resume(user, settings)
    usage = Usage()
    posting = rows[0]["posting"]
    try:
        draft = draft_follow_up(
            client, settings.analysis_model, resume_text, posting["title"], posting["company"], applied[-1][:10], usage
        )
    except (FollowUpError, anthropic.APIError) as error:
        raise HTTPException(502, f"Couldn't draft a follow-up: {error}")
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
    the next report raises RunStopped.
    """
    db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.queued"}, {"status": "running", "progress": "Starting…"})

    def report(message: str) -> None:
        if not db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running"}, {"progress": message}):
            raise RunStopped()

    return report


def finish_run(db: Rest, run_id: str, outcome: dict[str, Any], usage: Usage) -> None:
    """Saves a run's outcome while it's still running; a run the user stopped keeps its status and gets only its usage."""
    finished = {"usage": usage.model_dump(), "finished_at": datetime.now(UTC).isoformat()}
    if outcome and db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running"}, {**outcome, **finished}):
        return
    db.update("agent_runs", {"id": f"eq.{run_id}"}, {"usage": finished["usage"]})


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
    the company directory, every good or bad label, and jobs past "new".
    """
    service = service_db(settings)
    since = (datetime.now(UTC) - timedelta(days=STATS_DAYS)).isoformat()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "days": STATS_DAYS,
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
            {"select": "user_id,kind,status,created_at,usage", "created_at": f"gte.{since}", "order": "created_at.desc"},
        ),
        "companies": service.select("companies", {"select": "source,kind,open_jobs"}),
        "labels": service.select("applications", {"select": "fit_score,fit_label", "fit_label": "not.is.null"}),
        "applications": service.select("applications", {"select": "user_id,status", "status": "neq.new"}),
    }
