import io
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
from app.agents.schemas import AnthropicKeyRequest, CompanyImport, SearchRule, Usage
from app.auth import CurrentUser, current_user
from app.config import Settings, get_settings
from app.crypto import decrypt, encrypt, key_hint
from app.db import Rest, service_db, user_db
from app.sources.base import CompanyNotFound

logger = logging.getLogger("agent")

RUN_TIME_LIMIT = timedelta(minutes=10)
UNFINISHED = "in.(queued,running)"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Searches run inside this process, so any still unfinished at startup were cut off by a restart."""
    fail_runs(service_db(get_settings()), {"status": UNFINISHED}, "Stopped when the agent restarted. Re-run it.")
    yield


app = FastAPI(title="job-finder agent", lifespan=lifespan)

User = Annotated[CurrentUser, Depends(current_user)]
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
    try:
        make_client(body.api_key).models.retrieve(settings.scoring_model)
    except anthropic.AuthenticationError:
        raise HTTPException(400, "Anthropic rejected this key.")
    except anthropic.PermissionDeniedError:
        raise HTTPException(400, f"This key can't use {settings.scoring_model}.")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "Couldn't reach Anthropic to validate the key.")

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
    db.update("agent_runs", {"id": f"eq.{run_id}"}, {"status": "running", "progress": "Starting…"})

    def report(message: str) -> None:
        db.update("agent_runs", {"id": f"eq.{run_id}"}, {"progress": message})

    progress = None
    try:
        credentials = service.select(
            "api_credentials",
            {"user_id": f"eq.{user.id}", "provider": "eq.anthropic", "select": "ciphertext"},
        )
        if not credentials:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
        if not resumes or not resumes[0]["text"]:
            raise RuntimeError("Upload a resume first.")

        result = orchestrate_search(
            rule=body,
            client=make_client(decrypt(credentials[0]["ciphertext"], settings.agent_encryption_key)),
            settings=settings,
            resume_id=resumes[0]["id"],
            resume_text=resumes[0]["text"],
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
        )
        status, error, error_code = "done", None, None
        progress = summarize(result)
    except CompanyNotFound as exc:
        status, error, error_code = "failed", str(exc), "company_not_found"
    except Exception as exc:
        logger.exception("search run %s failed", run_id)
        status, error, error_code = "failed", str(exc) or exc.__class__.__name__, None

    db.update(
        "agent_runs",
        {"id": f"eq.{run_id}"},
        {
            "status": status,
            "error": error,
            "error_code": error_code,
            "progress": progress,
            "usage": usage.model_dump(),
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )


def extract_pdf_text(data: bytes) -> str:
    """Text of every page in order; empty for scanned PDFs with no text layer."""
    pages = (page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    lines = "\n".join(pages).splitlines()
    return "\n".join(line.strip() for line in lines if line.strip())


def summarize(result: SearchResult) -> str:
    """Final one-line progress for a finished search."""
    if result.company and result.found == 0:
        return f"Found {result.company}, but it has no open jobs listed."
    companies = "1 company" if result.companies == 1 else f"{result.companies} companies"
    unreachable = f" Couldn't reach {result.unreachable} more." if result.unreachable else ""
    if result.matched == 0:
        return f"Found {result.found} open jobs at {companies}, none match.{unreachable}"
    if result.kept < result.scored:
        parts = [f"Scored {result.scored} jobs from {companies} and kept the top {result.kept}"]
    else:
        parts = [f"Scored and saved {result.scored} jobs from {companies}"]
    if result.failed:
        parts.append(f"{result.failed} failed")
    if result.already_tracked:
        parts.append(f"skipped {result.already_tracked} already tracked")
    if result.unreachable:
        parts.append(f"couldn't reach {result.unreachable} {'company' if result.unreachable == 1 else 'companies'}")
    return ", ".join(parts) + "."


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
    db.update("agent_runs", {"id": f"eq.{run_id}"}, {"status": "running", "progress": "Starting…"})

    def report(message: str) -> None:
        db.update("agent_runs", {"id": f"eq.{run_id}"}, {"progress": message})

    progress = None
    try:
        credentials = service.select(
            "api_credentials",
            {"user_id": f"eq.{user.id}", "provider": "eq.anthropic", "select": "ciphertext"},
        )
        if not credentials:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        resumes = db.select("resumes", {"is_primary": "eq.true", "select": "id,text"})
        if not resumes or not resumes[0]["text"]:
            raise RuntimeError("Upload a resume first.")

        count = orchestrate_rescore(
            client=make_client(decrypt(credentials[0]["ciphertext"], settings.agent_encryption_key)),
            settings=settings,
            resume_id=resumes[0]["id"],
            resume_text=resumes[0]["text"],
            user_id=user.id,
            user=db,
            service=service,
            usage=usage,
            report=report,
        )
        status, error = "done", None
        progress = (
            f"Re-scored {count} {'job' if count == 1 else 'jobs'} with your current resume."
            if count
            else "Every job is already scored with your current resume."
        )
    except Exception as exc:
        logger.exception("rescore run %s failed", run_id)
        status, error = "failed", str(exc) or exc.__class__.__name__

    db.update(
        "agent_runs",
        {"id": f"eq.{run_id}"},
        {
            "status": status,
            "error": error,
            "progress": progress,
            "usage": usage.model_dump(),
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )


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
    db.update("agent_runs", {"id": f"eq.{run_id}"}, {"status": "running", "progress": "Starting…"})

    def report(message: str) -> None:
        db.update("agent_runs", {"id": f"eq.{run_id}"}, {"progress": message})

    progress = None
    try:
        credentials = service.select(
            "api_credentials",
            {"user_id": f"eq.{user.id}", "provider": "eq.anthropic", "select": "ciphertext"},
        )
        if not credentials:
            raise RuntimeError("Add your Anthropic API key in Settings first.")

        result = import_companies(
            entries=body.entries,
            client=make_client(decrypt(credentials[0]["ciphertext"], settings.agent_encryption_key)),
            settings=settings,
            service=service,
            usage=usage,
            report=report,
        )
        status, error = "done", None
        progress = summarize_import(result)
    except Exception as exc:
        logger.exception("import run %s failed", run_id)
        status, error = "failed", str(exc) or exc.__class__.__name__

    db.update(
        "agent_runs",
        {"id": f"eq.{run_id}"},
        {
            "status": status,
            "error": error,
            "progress": progress,
            "usage": usage.model_dump(),
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )


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
