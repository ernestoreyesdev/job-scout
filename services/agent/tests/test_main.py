from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException

from app import main
from app.agents.orchestrator import ImportResult, SearchResult
from app.agents.schemas import FollowUpDraft, GapAnalysis, GapItem, SearchRule
from app.sources.base import CompanyNotFound


class FakeRest:
    def __init__(self, conflict: bool = False):
        self.conflict = conflict
        self.updates: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.inserts: list[tuple[str, Any]] = []

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((table, filters, patch))
        return []

    def insert(self, table: str, rows: Any, on_conflict: str | None = None) -> list[dict[str, Any]]:
        if self.conflict:
            response = httpx.Response(409, request=httpx.Request("POST", "http://db/rest/v1/agent_runs"))
            raise httpx.HTTPStatusError("conflict", request=response.request, response=response)
        self.inserts.append((table, rows))
        return [{"id": "run-1"}]


def start(monkeypatch: pytest.MonkeyPatch, db: FakeRest) -> dict[str, str]:
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    user = SimpleNamespace(id="user-1", access_token="token")
    return main.start_search(SearchRule(keywords=["engineer"]), user, SimpleNamespace(), BackgroundTasks())


def test_starting_a_search_first_fails_runs_older_than_the_limit(monkeypatch: pytest.MonkeyPatch):
    db = FakeRest()

    assert start(monkeypatch, db) == {"run_id": "run-1"}

    [(table, filters, patch)] = db.updates
    assert table == "agent_runs" and filters["status"] == "in.(queued,running)"
    assert filters["created_at"].startswith("lt.")
    assert patch["status"] == "failed" and patch["error"] == "Stopped after running for more than 10 minutes."


def test_a_second_search_while_one_runs_is_refused(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(HTTPException) as refused:
        start(monkeypatch, FakeRest(conflict=True))

    assert refused.value.status_code == 409
    assert refused.value.detail == "A search is already running. Wait for it to finish."


def test_summary_mentions_unreachable_companies():
    result = SearchResult(companies=30, found=900, matched=12, already_tracked=0, scored=10, failed=0, unreachable=2, kept=10)

    assert main.summarize(result) == "Scored and saved 10 jobs from 30 companies, couldn't reach 2 companies."


class RunRest(FakeRest):
    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "api_credentials":
            return [{"ciphertext": "secret"}]
        return [{"id": "resume-1", "text": "Python developer."}]


def test_a_company_that_isnt_found_fails_with_its_error_code(monkeypatch: pytest.MonkeyPatch):
    db = RunRest()
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    monkeypatch.setattr(main, "service_db", lambda settings: db)
    monkeypatch.setattr(main, "decrypt", lambda ciphertext, key: "key")

    def not_found(**kwargs: Any) -> SearchResult:
        raise CompanyNotFound("Couldn't find job listings for Publix.")

    monkeypatch.setattr(main, "orchestrate_search", not_found)
    settings = SimpleNamespace(agent_encryption_key="k")

    main.run_search("run-1", SearchRule(company="Publix", keywords=["engineer"]), SimpleNamespace(id="u", access_token="t"), settings)

    final = db.updates[-1][2]
    assert (final["status"], final["error_code"]) == ("failed", "company_not_found")
    assert final["error"] == "Couldn't find job listings for Publix."


def test_summary_says_when_a_company_has_no_open_jobs():
    result = SearchResult(companies=1, found=0, matched=0, already_tracked=0, scored=0, failed=0, company="Publix")

    assert main.summarize(result) == "Found Publix, but it has no open jobs listed."


def test_summary_says_how_many_of_the_scored_jobs_were_kept():
    result = SearchResult(companies=4, found=300, matched=40, already_tracked=0, scored=20, failed=0, kept=10)

    assert main.summarize(result) == "Scored 20 jobs from 4 companies and kept the top 10."


def test_import_summary_names_companies_with_no_open_jobs():
    result = ImportResult(added=["Acme", "Boeing"], existing=1, not_found=["Nowhere"], empty=["Boeing"])

    assert main.summarize_import(result) == (
        "Added 2 companies, Boeing has no open jobs listed, 1 already in the directory, couldn't find Nowhere."
    )


class JobRest(FakeRest):
    """Answers selects for one application, the user's key and primary resume."""

    def __init__(self, application: dict[str, Any] | None):
        super().__init__()
        self.application = application

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "applications":
            return [self.application] if self.application else []
        if table == "api_credentials":
            return [{"ciphertext": "secret"}]
        return [{"text": "Python developer, 8 years."}]


def call_job_endpoint(monkeypatch: pytest.MonkeyPatch, endpoint: Any, db: JobRest, **fakes: Any) -> dict[str, Any]:
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    monkeypatch.setattr(main, "service_db", lambda settings: db)
    monkeypatch.setattr(main, "decrypt", lambda ciphertext, key: "key")
    monkeypatch.setattr(main, "make_client", lambda key: None)
    for name, fake in fakes.items():
        monkeypatch.setattr(main, name, fake)
    settings = SimpleNamespace(agent_encryption_key="k", analysis_model="claude-haiku-5-5")
    return endpoint("app-1", SimpleNamespace(id="u", access_token="t"), settings)


POSTING = {
    "source": "lever",
    "board": "acme",
    "external_id": "1",
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Remote",
    "url": "https://example.com/1",
    "description": "Python and Postgres.",
    "posted_at": None,
}


def test_gap_analysis_is_saved_on_the_application(monkeypatch: pytest.MonkeyPatch):
    analysis = GapAnalysis(
        covered=[GapItem(requirement="Python", evidence="8 years of Python", suggestion="Lead with it.")],
        weak=[],
        missing=[GapItem(requirement="Postgres", evidence="", suggestion="Mention SQL work the resume shows.")],
    )
    db = JobRest({"id": "app-1", "posting": POSTING})

    result = call_job_endpoint(
        monkeypatch, main.post_gap_analysis, db, analyze_gaps=lambda client, model, resume, posting, usage: analysis
    )

    assert result["gap_analysis"] == analysis.model_dump()
    [(table, filters, patch)] = db.updates
    assert (table, filters) == ("applications", {"id": "eq.app-1"})
    assert patch["gap_analysis"] == analysis.model_dump() and patch["gap_analyzed_at"]


def test_gap_analysis_of_someone_elses_job_is_not_found(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(HTTPException) as missing:
        call_job_endpoint(monkeypatch, main.post_gap_analysis, JobRest(None))

    assert missing.value.status_code == 404


def test_follow_up_uses_the_latest_applied_date(monkeypatch: pytest.MonkeyPatch):
    seen: list[str] = []

    def draft(client: Any, model: str, resume: str, title: str, company: str, applied_on: str, usage: Any) -> FollowUpDraft:
        seen.append(applied_on)
        return FollowUpDraft(subject="Following up", body="Hi team")

    events = [
        {"status": "saved", "changed_at": "2026-10-01T10:00:00+00:00"},
        {"status": "applied", "changed_at": "2026-10-03T10:00:00+00:00"},
        {"status": "applied", "changed_at": "2026-10-20T10:00:00+00:00"},
    ]
    db = JobRest({"id": "app-1", "posting": {"title": "Backend Engineer", "company": "Acme"}, "events": events})

    result = call_job_endpoint(monkeypatch, main.post_follow_up, db, draft_follow_up=draft)

    assert seen == ["2026-10-20"] and (result["subject"], result["body"]) == ("Following up", "Hi team")


def test_follow_up_needs_an_applied_job(monkeypatch: pytest.MonkeyPatch):
    db = JobRest({"id": "app-1", "posting": {"title": "T", "company": "C"}, "events": [{"status": "saved", "changed_at": "x"}]})

    with pytest.raises(HTTPException) as refused:
        call_job_endpoint(monkeypatch, main.post_follow_up, db)

    assert refused.value.status_code == 400
