import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.schemas import FitScore, JobDetails, RunStopped, Usage
from app.agents.scoring.prompts import FIT_SYSTEM, LabeledJob, fit_blocks
from app.db import Rest
from app.sources.base import Posting
from app.telemetry import ContextThreadPool

logger = logging.getLogger("agent")

SCORE_CONCURRENCY = 8


class ScoringError(Exception):
    pass


@dataclass
class ScoringResult:
    """How many jobs were scored and failed, and each scored posting id's score."""

    scored: int
    failed: int
    scores: dict[str, int] = field(default_factory=dict)


def score_posting(
    client: Any, model: str, effort: str, resume_text: str, posting: Posting, examples: Sequence[LabeledJob] = ()
) -> tuple[FitScore, Any]:
    """
    One Claude call: the resume, the user's labeled examples and one job in, a
    structured fit score out. Returns the score and its usage.
    """
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort},
        system=FIT_SYSTEM,
        messages=[{"role": "user", "content": fit_blocks(resume_text, posting, examples)}],
        output_format=FitScore,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ScoringError(f"Scoring failed (stop reason: {response.stop_reason}).")
    return response.parsed_output, response.usage


def score_and_save(
    *,
    client: Any,
    model: str,
    effort: str,
    todo: list[tuple[str, Posting]],
    resume_id: str,
    resume_text: str,
    user_id: str,
    user: Rest,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    examples: Sequence[LabeledJob] = (),
    min_score: int | None = None,
) -> ScoringResult:
    """
    Scores each (posting id, posting) pair and saves it to the user's tracker as
    soon as it's scored, along with the facts read from the posting; a job
    scoring below `min_score` is saved off the Tracker. The first job is scored
    alone so the cached resume prefix exists before the parallel calls start.
    """
    lock = threading.Lock()
    done = {"scored": 0, "failed": 0}
    scores: dict[str, int] = {}

    def score_one(posting_id: str, posting: Posting) -> None:
        fit, call_usage = score_posting(client, model, effort, resume_text, posting, examples)
        user.insert(
            "applications",
            {
                "user_id": user_id,
                "posting_id": posting_id,
                "resume_id": resume_id,
                "fit_score": fit.score,
                "fit_summary": fit.summary,
                "strengths": fit.strengths,
                "gaps": fit.gaps,
                **({"in_tracker": False} if min_score is not None and fit.score < min_score else {}),
            },
            on_conflict="user_id,posting_id",
        )
        service.update("postings", {"id": f"eq.{posting_id}"}, posting_details(fit.details, posting))
        with lock:
            usage.add(call_usage)
            scores[posting_id] = fit.score
            done["scored"] += 1
            report(f"Scoring jobs against your resume ({done['scored']} of {len(todo)})…")

    if not todo:
        return ScoringResult(0, 0)

    # A failure on the first job (bad key, model unavailable) would repeat for every job, so it ends the run.
    score_one(*todo[0])

    with ContextThreadPool(max_workers=SCORE_CONCURRENCY) as pool:
        futures = {pool.submit(score_one, posting_id, posting): posting for posting_id, posting in todo[1:]}
        for future in as_completed(futures):
            if isinstance(future.exception(), RunStopped):
                pool.shutdown(cancel_futures=True)
                raise RunStopped()
            if future.exception() is not None:
                logger.warning("scoring %s failed: %s", futures[future].title, future.exception())
                with lock:
                    done["failed"] += 1

    return ScoringResult(done["scored"], done["failed"], scores)


def posting_details(details: JobDetails, posting: Posting) -> dict[str, Any]:
    """Columns saved on the posting; the source's own workplace type wins over the one read from the text."""
    columns = details.model_dump(exclude={"workplace_type"})
    columns["details_extracted_at"] = datetime.now(UTC).isoformat()
    if posting.workplace_type is None and details.workplace_type is not None:
        columns["workplace_type"] = details.workplace_type
    return columns
