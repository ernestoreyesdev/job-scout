from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException

from app import main
from app.agents.orchestrator import ImportResult, SearchResult
from app.agents.schemas import SearchRule
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
