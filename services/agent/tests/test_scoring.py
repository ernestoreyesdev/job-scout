import threading
from types import SimpleNamespace
from typing import Any, cast

from app.agents.schemas import FitScore, JobDetails
from app.agents.scoring.agent import score_and_save, steady_score
from app.agents.scoring.prompts import trim_description
from app.db import Rest
from app.sources.base import Posting
from tests.fakes import claude

ROLE = "About the role\nBuild payments infrastructure.\n\nRequirements\n- 5 years of Python\n- Distributed systems\n"


def test_trim_drops_benefits_and_legal_text_at_the_end():
    description = ROLE + "BENEFITS AVAILABLE TO ALL EMPLOYEES\n- Health insurance\n\nEqual Opportunity\nWe welcome everyone."

    assert trim_description(description) == ROLE.rstrip()


def test_trim_keeps_a_heading_near_the_start():
    description = "Benefits team engineer\n" + ROLE

    assert trim_description(description) == description


def test_trim_keeps_text_without_boilerplate():
    assert trim_description(ROLE) == ROLE


def test_trim_keeps_pay_lines_from_the_text_it_drops():
    description = ROLE + "Benefits\n- Health insurance\n\nPay Transparency\nThe base salary range is $150,000 - $190,000 USD.\n"

    assert trim_description(description) == (
        ROLE.rstrip() + "\n\nPay stated later in the posting:\nThe base salary range is $150,000 - $190,000 USD."
    )




class SequenceMessages:
    """A Claude client's messages whose parse returns the next of `scores` as a fit score."""

    def __init__(self, scores: list[int]):
        self.scores = iter(scores)
        self.calls = 0
        self.lock = threading.Lock()

    def parse(self, **_: Any) -> SimpleNamespace:
        with self.lock:
            self.calls += 1
            score = next(self.scores)
        fit = FitScore(
            score=score,
            summary=f"Scored {score}.",
            strengths=[],
            gaps=[],
            details=JobDetails(
                salary_min=None,
                salary_max=None,
                salary_currency=None,
                salary_period=None,
                clearance=None,
                visa_sponsorship=None,
                years_experience=None,
                tech_stack=[],
                workplace_type=None,
            ),
        )
        return SimpleNamespace(parsed_output=fit, stop_reason="end_turn", usage=SimpleNamespace(input_tokens=0, output_tokens=0))


class SavedRows:
    def __init__(self):
        self.inserts: list[dict[str, Any]] = []

    def insert(self, table: str, rows: Any, on_conflict: str | None = None, select: str | None = None) -> list[dict[str, Any]]:
        self.inserts.append(rows)
        return [rows]

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        return []


def score_one(scores: list[int], min_score: int | None = None) -> tuple[dict[str, Any], int]:
    """Scores one job with Claude answering `scores` in turn; returns the saved row and how many calls were made."""
    messages = SequenceMessages(scores)
    user = SavedRows()
    job = Posting(
        source="ashby",
        board="acme",
        external_id="1",
        title="Software Engineer",
        company="Acme",
        location="Remote",
        url="https://example.com/1",
        description="Build things.",
        posted_at=None,
    )
    score_and_save(
        client=claude(messages),
        model="claude-haiku-5-5",
        effort="low",
        todo=[("posting-1", job)],
        resume_id="resume-1",
        resume_text="Engineer.",
        user_id="user-1",
        user=cast(Rest, user),
        service=cast(Rest, SavedRows()),
        report=lambda _: None,
        min_score=min_score,
    )
    return user.inserts[0], messages.calls


def test_a_score_near_a_cut_is_scored_twice_more_and_averaged():
    saved, calls = score_one([45, 55, 56])

    assert calls == 3
    assert saved["fit_score"] == 52 and saved["fit_summary"] == "Scored 45."


def test_a_score_far_from_every_cut_is_scored_once():
    saved, calls = score_one([90])

    assert calls == 1 and saved["fit_score"] == 90


def test_the_minimum_score_is_checked_against_the_average():
    saved, _ = score_one([45, 55, 56], min_score=50)

    assert saved["fit_score"] == 52 and "in_tracker" not in saved


def test_the_extra_scores_run_at_the_same_time():
    both_running = threading.Barrier(2, timeout=5)

    def again() -> int:
        both_running.wait()
        return 60

    assert steady_score(54, again) == 58
