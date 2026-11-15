from datetime import UTC, datetime, timedelta
from typing import Any

from app.agents.lessons import agent
from app.agents.lessons.agent import MAX_LESSONS, MIN_JOBS, fingerprint, merged, refresh_lessons
from app.agents.lessons.prompts import job_line
from app.agents.orchestrator import current_lessons
from app.agents.schemas import LearnedLesson, LessonUpdate
from app.agents.scoring.prompts import Lesson, fit_blocks
from app.db import Rest
from tests.fakes import FakeParse, claude
from tests.test_orchestrator import JOBS, SETTINGS

NOW = datetime(2026, 11, 15, tzinfo=UTC)
FACTS = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Austin, TX",
    "workplace_type": "remote",
    "years_experience": 5,
    "tech_stack": ["Python", "AWS"],
    "salary_min": 150000,
    "salary_max": 190000,
    "salary_currency": "USD",
    "salary_period": "year",
    "clearance": None,
    "visa_sponsorship": None,
}


def lesson(lesson_id: str, text: str, source: str = "learned", days_old: int = 1, deleted: bool = False) -> dict[str, Any]:
    return {
        "id": lesson_id,
        "text": text,
        "source": source,
        "evidence": 3,
        "confirmed_at": (NOW - timedelta(days=days_old)).isoformat(),
        "deleted_at": NOW.isoformat() if deleted else None,
    }


def job(posting_id: str, label: str | None = "good", status: str = "saved") -> dict[str, Any]:
    return {"posting_id": posting_id, "fit_label": label, "status": status, "posting": FACTS}


def learned(text: str, restates: int | None = None) -> LearnedLesson:
    return LearnedLesson(text=text, evidence=4, restates=restates)


class LessonRest(Rest):
    def __init__(self, jobs: list[dict[str, Any]], lessons: list[dict[str, Any]], mark: str | None = None):
        self.jobs = jobs
        self.lessons = lessons
        self.mark = mark
        self.inserts: list[tuple[str, Any]] = []

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "applications":
            return self.jobs
        if table == "profiles":
            return [{"lessons_fingerprint": self.mark}] if self.mark else []
        return self.lessons

    def insert(self, table: str, rows: Any, on_conflict: str | None = None, select: str | None = None) -> list[dict[str, Any]]:
        self.inserts.append((table, rows))
        return []

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def delete(self, table: str, filters: dict[str, str]) -> None:
        pass


def test_a_lesson_that_restates_a_current_one_confirms_it():
    changes = merged([lesson("a", "Likes remote roles")], LessonUpdate(lessons=[learned("Prefers remote roles", 1)], contradicted=[]), "u", NOW)

    assert changes.updates == [("a", {"text": "Prefers remote roles", "evidence": 4, "confirmed_at": NOW.isoformat()})]
    assert changes.inserts == [] and changes.deletes == []


def test_contradicted_and_faded_lessons_are_deleted_and_unconfirmed_ones_stay():
    rows = [lesson("a", "Prefers remote roles"), lesson("b", "Avoids startups"), lesson("c", "Wants Go", days_old=61)]

    changes = merged(rows, LessonUpdate(lessons=[], contradicted=[2]), "u", NOW)

    assert changes.deletes == ["b", "c"]


def test_deleted_and_user_written_lessons_are_not_learned_again():
    rows = [lesson("a", "Avoids startups", deleted=True), lesson("b", "No clearance jobs", source="user")]
    update = LessonUpdate(lessons=[learned("avoids startups"), learned("No clearance jobs "), learned("Prefers remote roles")], contradicted=[])

    changes = merged(rows, update, "u", NOW)

    assert [row["text"] for row in changes.inserts] == ["Prefers remote roles"]
    assert changes.inserts[0]["source"] == "learned" and changes.inserts[0]["user_id"] == "u"


def test_new_lessons_stop_at_the_limit():
    rows = [lesson(str(n), f"Lesson {n}") for n in range(MAX_LESSONS - 1)]
    update = LessonUpdate(lessons=[learned("New one"), learned("Another")], contradicted=[])

    assert [row["text"] for row in merged(rows, update, "u", NOW).inserts] == ["New one"]


def test_the_fingerprint_changes_with_a_rating_or_an_application_and_not_with_order():
    jobs = [job("1"), job("2", "bad")]

    assert fingerprint(jobs) == fingerprint(jobs[::-1])
    assert fingerprint(jobs) != fingerprint([job("1"), job("2", "good")])
    assert fingerprint(jobs) != fingerprint([job("1", status="applied"), job("2", "bad")])
    assert fingerprint(jobs) == fingerprint([job("1", status="saved"), job("2", "bad", status="new")])


def test_lessons_are_learned_again_only_when_the_signals_changed():
    jobs = [job(str(n)) for n in range(MIN_JOBS)]
    update = LessonUpdate(lessons=[learned("Prefers remote roles")], contradicted=[])

    unchanged = FakeParse(update)
    refresh_lessons(claude(unchanged), "m", LessonRest(jobs, [], fingerprint(jobs)), "u", NOW)
    too_few = FakeParse(update)
    refresh_lessons(claude(too_few), "m", LessonRest(jobs[1:], []), "u", NOW)
    changed, db = FakeParse(update), LessonRest(jobs, [], "old")
    refresh_lessons(claude(changed), "m", db, "u", NOW)

    assert unchanged.calls == [] and too_few.calls == []
    assert [table for table, _ in db.inserts] == ["lessons", "profiles"]
    assert db.inserts[1][1] == {"user_id": "u", "lessons_fingerprint": fingerprint(jobs)}


def test_a_failed_update_scores_with_the_saved_lessons(monkeypatch):
    def fail(*args: Any) -> None:
        raise RuntimeError("overloaded")

    monkeypatch.setattr("app.agents.orchestrator.refresh_lessons", fail)
    db = LessonRest([], [{"text": "No clearance jobs", "source": "user"}])

    assert current_lessons(None, SETTINGS, db, "u") == [Lesson("No clearance jobs", "user")]


def test_saved_lessons_keep_the_users_own_and_recently_confirmed_learned_ones():
    class Recording(LessonRest):
        params: dict[str, str]

        def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
            self.params = params
            return []

    db = Recording([], [])
    agent.saved_lessons(db, NOW)

    assert db.params["deleted_at"] == "is.null"
    assert db.params["or"] == f"(source.eq.user,confirmed_at.gt.{(NOW - timedelta(days=60)).isoformat()})"


def test_a_job_line_lists_what_the_user_did_and_the_postings_facts():
    assert job_line(job("1", "good", "applied")) == (
        "rated good, applied: Backend Engineer | Acme | Austin, TX (remote) | 5+ years | Python, AWS | 150000-190000 USD a year"
    )
    assert job_line(job("1", None, "interviewing")).startswith("interviewing: ")


def test_lessons_go_in_the_cached_block_as_rules_and_tendencies():
    blocks = fit_blocks("Resume.", JOBS[0], lessons=[Lesson("No clearance jobs", "user"), Lesson("Prefers remote roles", "learned")])

    assert "<lessons>\nrule: No clearance jobs\ntendency: Prefers remote roles\n</lessons>" in blocks[0]["text"]
    assert "lessons" not in blocks[1]["text"]
