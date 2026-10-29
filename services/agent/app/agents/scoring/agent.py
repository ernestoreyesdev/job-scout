import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from app.agents.schemas import FitScore, Usage
from app.agents.scoring.prompts import FIT_SYSTEM, fit_blocks
from app.db import Rest
from app.sources.base import Posting

logger = logging.getLogger("agent")

SCORE_CONCURRENCY = 4


class ScoringError(Exception):
    pass


@dataclass
class ScoringResult:
    scored: int
    failed: int


def score_posting(client: Any, model: str, effort: str, resume_text: str, posting: Posting) -> tuple[FitScore, Any]:
    """One Claude call: the resume and one job in, a structured fit score out. Returns the score and its usage."""
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort},
        system=FIT_SYSTEM,
        messages=[{"role": "user", "content": fit_blocks(resume_text, posting)}],
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
    usage: Usage,
    report: Callable[[str], None],
) -> ScoringResult:
    """
    Scores each (posting id, posting) pair and saves it to the user's tracker as
    soon as it's scored. The first job is scored alone so the cached resume
    prefix exists before the parallel calls start.
    """
    lock = threading.Lock()
    done = {"scored": 0, "failed": 0}

    def score_one(posting_id: str, posting: Posting) -> None:
        fit, call_usage = score_posting(client, model, effort, resume_text, posting)
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
            },
            on_conflict="user_id,posting_id",
        )
        with lock:
            usage.add(call_usage)
            done["scored"] += 1
            report(f"Scored {done['scored']} of {len(todo)}: {posting.title} at {posting.company}")

    if not todo:
        return ScoringResult(0, 0)

    # A failure on the first job (bad key, model unavailable) would repeat for every job, so it ends the run.
    score_one(*todo[0])

    with ThreadPoolExecutor(max_workers=SCORE_CONCURRENCY) as pool:
        futures = {pool.submit(score_one, posting_id, posting): posting for posting_id, posting in todo[1:]}
        for future in as_completed(futures):
            if future.exception() is not None:
                logger.warning("scoring %s failed: %s", futures[future].title, future.exception())
                with lock:
                    done["failed"] += 1

    return ScoringResult(done["scored"], done["failed"])
