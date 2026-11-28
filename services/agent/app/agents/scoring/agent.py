import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.claude import parse
from app.agents.schemas import FitScore, JobDetails, RunStopped
from app.agents.scoring.prompts import FIT_STEP, FIT_SYSTEM, LabeledJob, Lesson, fit_blocks
from app.constants import POSSIBLE_FIT_SCORE, STRONG_FIT_SCORE
from app.db import Rest
from app.sources.base import Posting, description_hash
from app.telemetry import ContextThreadPool, prompt_version

logger = logging.getLogger("agent")

SCORE_CONCURRENCY = 8
MAX_TOKENS = 16000
# The Possible and Strong fit labels' lowest scores; a first score within NEAR_CUT of one is scored EXTRA_SCORES more times.
SCORE_CUTS = (POSSIBLE_FIT_SCORE, STRONG_FIT_SCORE)
NEAR_CUT = 10
EXTRA_SCORES = 2


class ScoringError(Exception):
    pass


@dataclass
class ScoringResult:
    """How many jobs were scored and failed, and each scored posting id's score."""

    scored: int
    failed: int
    scores: dict[str, int] = field(default_factory=dict)


def score_posting(
    client: Any,
    model: str,
    effort: str,
    resume_text: str,
    posting: Posting,
    examples: Sequence[LabeledJob] = (),
    lessons: Sequence[Lesson] = (),
) -> FitScore:
    """One Claude call: the resume, the user's labeled examples and lessons and one job in, a structured fit score out."""
    return parse(
        client,
        model=model,
        max_tokens=MAX_TOKENS,
        effort=effort,
        step=FIT_STEP,
        system=FIT_SYSTEM,
        content=fit_blocks(resume_text, posting, examples, lessons),
        output_format=FitScore,
        error=ScoringError,
        failure="Scoring",
    )


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
    report: Callable[[str], None],
    examples: Sequence[LabeledJob] = (),
    lessons: Sequence[Lesson] = (),
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
        fit = score_posting(client, model, effort, resume_text, posting, examples, lessons)
        score = steady_score(fit.score, lambda: score_posting(client, model, effort, resume_text, posting, examples, lessons).score)
        user.insert(
            "applications",
            {
                "user_id": user_id,
                "posting_id": posting_id,
                "resume_id": resume_id,
                "fit_score": score,
                "fit_summary": fit.summary,
                "strengths": fit.strengths,
                "gaps": fit.gaps,
                "score_model": model,
                "score_prompt_version": prompt_version(FIT_SYSTEM, FitScore),
                **({"in_tracker": False} if min_score is not None and score < min_score else {}),
            },
            on_conflict="user_id,posting_id",
        )
        service.update("postings", {"id": f"eq.{posting_id}"}, posting_details(fit.details, posting))
        with lock:
            scores[posting_id] = score
            done["scored"] += 1
            scored = done["scored"]
        report(f"Scoring jobs against your resume ({scored} of {len(todo)})…")

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
    """
    Columns saved on the posting: the facts read from it and the description
    it was scored on. The source's own workplace type wins over the one read
    from the text.
    """
    columns = details.model_dump(exclude={"workplace_type"})
    columns["details_extracted_at"] = datetime.now(UTC).isoformat()
    columns["description"] = posting.description
    columns["description_hash"] = description_hash(posting.description)
    if posting.workplace_type is None and details.workplace_type is not None:
        columns["workplace_type"] = details.workplace_type
    return columns


def steady_score(first: int, again: Callable[[], int]) -> int:
    """
    The first score, or when it is near a cut, the rounded average of it and
    EXTRA_SCORES more from `again`, which run at the same time.
    """
    if all(abs(first - cut) > NEAR_CUT for cut in SCORE_CUTS):
        return first
    with ContextThreadPool(max_workers=EXTRA_SCORES) as pool:
        extra = list(pool.map(lambda _: again(), range(EXTRA_SCORES)))
    scores = [first, *extra]
    return round(sum(scores) / len(scores))
