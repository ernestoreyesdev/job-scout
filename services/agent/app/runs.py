"""
A run's life in agent_runs: started, reporting progress until the user stops
it, then saved with its outcome, usage, step timings and Claude calls.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.agents.schemas import RunError, RunStopped, Usage
from app.db import Rest
from app.telemetry import CallLog, RecordingClient, current_run

logger = logging.getLogger("agent")

UNFINISHED = "in.(queued,running)"
# What users see when a run of each kind fails unexpectedly; the original error goes to run_errors.
RUN_FAILED = {
    "search": "Something went wrong with this search. Try running it again.",
    "rescore": "Something went wrong while rescoring. Try again.",
    "import": "Something went wrong while adding these companies. Try again.",
}


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
        if not db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running", "select": "id"}, {"progress": message}):
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
    if outcome and db.update("agent_runs", {"id": f"eq.{run_id}", "status": "eq.running", "select": "id"}, {**outcome, **finished}):
        return
    db.update("agent_runs", {"id": f"eq.{run_id}"}, measured)


def save_run_error(service: Rest, run_id: str, detail: str | None) -> None:
    """Keeps the original error of a run that failed unexpectedly, for the admin page."""
    if detail:
        service.insert("run_errors", {"run_id": run_id, "detail": detail})


def record_run(
    run_id: str,
    kind: str,
    db: Rest,
    service: Rest,
    connect: Callable[[], Any],
    work: Callable[[Any, Rest, Rest, Callable[[str], None], dict[str, int]], dict[str, Any]],
) -> dict[str, Any]:
    """
    Starts a queued run, then runs `work` with the Claude client from `connect`
    recording its calls, the user's database, the service database, the progress
    reporter and the step timings, and saves its outcome, usage and Claude calls.
    A RunError fails the run with its message; any other error fails it with
    RUN_FAILED and is kept in run_errors. Returns the outcome, empty when the
    user stopped the run.
    """
    report = start_run(db, run_id)
    calls, timings = CallLog(run_id), {}
    outcome: dict[str, Any] = {}
    detail: str | None = None
    try:
        outcome = work(RecordingClient(connect(), calls), db, service, report, timings)
    except RunStopped:
        pass
    except RunError as exc:
        outcome = {"status": "failed", "error": str(exc), "error_code": None, "progress": None}
    except Exception as exc:
        logger.exception("%s run %s failed", kind, run_id)
        detail = f"{exc.__class__.__name__}: {exc}"
        outcome = {"status": "failed", "error": RUN_FAILED[kind], "error_code": None, "progress": None}

    finish_run(db, run_id, outcome, calls.usage(), timings)
    save_run_error(service, run_id, detail)
    calls.save(service)
    return outcome
