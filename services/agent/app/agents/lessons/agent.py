import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.agents.claude import parse
from app.agents.lessons.prompts import LESSONS_SYSTEM, MAX_LESSONS, WANTED_STATUSES, lessons_message
from app.agents.schemas import LessonUpdate
from app.agents.scoring.prompts import Lesson
from app.db import Rest

# Jobs needed before any lessons are learned, and the most recent jobs they're learned from.
MIN_JOBS = 5
MAX_JOBS = 100
# A learned lesson no update has confirmed for this long is dropped.
FADE_AFTER = timedelta(days=60)
JOB_FACTS = (
    "title,company,location,workplace_type,years_experience,tech_stack,"
    "salary_min,salary_max,salary_currency,salary_period,clearance,visa_sponsorship"
)
LESSON_COLUMNS = "id,text,source,evidence,confirmed_at,deleted_at"
MAX_TOKENS = 4000


class LessonsError(Exception):
    pass


@dataclass
class LessonChanges:
    """The rows an update adds, the (id, patch) pairs it changes and the ids it deletes."""

    inserts: list[dict[str, Any]] = field(default_factory=list)
    updates: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)


def signal_jobs(user: Rest) -> list[dict[str, Any]]:
    """The user's most recently updated jobs that are rated or applied to, with the facts read from each posting."""
    return user.select(
        "applications",
        {
            "select": f"posting_id,fit_label,status,posting:postings({JOB_FACTS})",
            "or": f"(fit_label.not.is.null,status.in.({','.join(WANTED_STATUSES)}))",
            "order": "updated_at.desc",
            "limit": str(MAX_JOBS),
        },
    )


def fingerprint(jobs: list[dict[str, Any]]) -> str:
    """Changes whenever a job is rated, re-rated, applied to or moves along, and only then."""
    marks = sorted(f"{job['posting_id']}:{job['fit_label']}:{job['status'] in WANTED_STATUSES}" for job in jobs)
    return hashlib.sha256("\n".join(marks).encode()).hexdigest()


def learn(client: Any, model: str, current: list[str], own: list[str], deleted: list[str], jobs: list[dict[str, Any]]) -> LessonUpdate:
    """One call that rewrites the learned lessons from the jobs, numbering the current ones it confirms or contradicts."""
    return parse(
        client,
        model=model,
        max_tokens=MAX_TOKENS,
        system=LESSONS_SYSTEM,
        content=lessons_message(current, own, deleted, jobs),
        output_format=LessonUpdate,
        error=LessonsError,
        failure="Learning preferences",
    )


def active(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """The learned lessons not deleted and confirmed within FADE_AFTER, in their order."""
    return [
        row
        for row in rows
        if row["source"] == "learned" and row["deleted_at"] is None and datetime.fromisoformat(row["confirmed_at"]) > now - FADE_AFTER
    ]


def merged(rows: list[dict[str, Any]], update: LessonUpdate, user_id: str, now: datetime) -> LessonChanges:
    """
    Applies an update to the user's lessons: a lesson that restates a current
    one confirms it, a contradicted or faded one is deleted, and a new one is
    added unless it repeats a deleted or user-written lesson or the user already
    has MAX_LESSONS learned ones.
    """
    current = active(rows, now)
    taken = {
        row["text"].strip().casefold() for row in rows if row["deleted_at"] is not None or row["source"] == "user"
    }
    changes = LessonChanges()
    confirmed: set[int] = set()
    added: list[dict[str, Any]] = []
    for lesson in update.lessons:
        if lesson.restates is not None and 1 <= lesson.restates <= len(current) and lesson.restates not in confirmed:
            confirmed.add(lesson.restates)
            patch = {"text": lesson.text, "evidence": lesson.evidence, "confirmed_at": now.isoformat()}
            changes.updates.append((current[lesson.restates - 1]["id"], patch))
        elif lesson.text.strip().casefold() not in taken:
            taken.add(lesson.text.strip().casefold())
            added.append(
                {"user_id": user_id, "text": lesson.text, "source": "learned", "evidence": lesson.evidence, "confirmed_at": now.isoformat()}
            )
    contradicted = {n for n in update.contradicted if 1 <= n <= len(current)} - confirmed
    faded = [row for row in rows if row["source"] == "learned" and row["deleted_at"] is None and row not in current]
    changes.deletes = [current[n - 1]["id"] for n in sorted(contradicted)] + [row["id"] for row in faded]
    changes.inserts = added[: max(0, MAX_LESSONS - (len(current) - len(contradicted)))]
    return changes


def relearn(client: Any, model: str, user: Rest, user_id: str, jobs: list[dict[str, Any]], now: datetime) -> None:
    """Learns the user's lessons again from `jobs` and saves them with the jobs' fingerprint."""
    rows = user.select("lessons", {"select": LESSON_COLUMNS, "order": "created_at"})
    current = [row["text"] for row in active(rows, now)]
    own = [row["text"] for row in rows if row["source"] == "user" and row["deleted_at"] is None]
    deleted = [row["text"] for row in rows if row["deleted_at"] is not None]
    changes = merged(rows, learn(client, model, current, own, deleted, jobs), user_id, now)
    for lesson_id, patch in changes.updates:
        user.update("lessons", {"id": f"eq.{lesson_id}"}, patch)
    if changes.deletes:
        user.delete("lessons", {"id": f"in.({','.join(changes.deletes)})"})
    if changes.inserts:
        user.insert("lessons", changes.inserts)
    user.insert("profiles", {"user_id": user_id, "lessons_fingerprint": fingerprint(jobs)}, on_conflict="user_id")


def refresh_lessons(client: Any, model: str, user: Rest, user_id: str, now: datetime) -> None:
    """Learns the user's lessons again when they have MIN_JOBS signals and their ratings or statuses changed since the last time."""
    jobs = signal_jobs(user)
    if len(jobs) < MIN_JOBS:
        return
    profile = user.select("profiles", {"select": "lessons_fingerprint"})
    if profile and profile[0]["lessons_fingerprint"] == fingerprint(jobs):
        return
    relearn(client, model, user, user_id, jobs, now)


def saved_lessons(user: Rest, now: datetime) -> list[Lesson]:
    """The user's own lessons and their learned ones confirmed within FADE_AFTER, oldest first."""
    rows = user.select(
        "lessons",
        {
            "select": "text,source",
            "deleted_at": "is.null",
            "or": f"(source.eq.user,confirmed_at.gt.{(now - FADE_AFTER).isoformat()})",
            "order": "created_at",
        },
    )
    return [Lesson(row["text"], row["source"]) for row in rows]
