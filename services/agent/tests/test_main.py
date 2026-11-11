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
    def __init__(self, conflict: bool = False, run_status: str = "queued"):
        self.conflict = conflict
        self.run_status = run_status
        self.updates: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.inserts: list[tuple[str, Any]] = []

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((table, filters, patch))
        wanted = filters.get("status")
        if wanted and self.run_status not in wanted.removeprefix("eq.").removeprefix("in.(").rstrip(")").split(","):
            return []
        self.run_status = patch.get("status", self.run_status)
        return [patch]

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
    assert patch["error_code"] == "timed_out"


def test_a_second_search_while_one_runs_is_refused(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(HTTPException) as refused:
        start(monkeypatch, FakeRest(conflict=True))

    assert refused.value.status_code == 409
    assert refused.value.detail == "A search is already running. Wait for it to finish."


def test_summary_says_how_many_jobs_were_added_without_internal_counts():
    scored_all = SearchResult(companies=30, found=900, matched=12, already_tracked=2, scored=10, failed=0, unreachable=2, kept=10)
    unscored = SearchResult(companies=5, found=90, matched=8, already_tracked=0, scored=0, failed=0, kept=1)
    nothing_new = SearchResult(companies=5, found=90, matched=8, already_tracked=8, scored=0, failed=0)
    no_match = SearchResult(companies=5, found=90, matched=0, already_tracked=0, scored=0, failed=0)

    assert main.summarize(scored_all) == "Added 10 jobs."
    assert main.summarize(unscored) == "Added the 1 newest job."
    assert main.summarize(nothing_new) == "No new jobs: every match is already on your list."
    assert main.summarize(no_match) == "No jobs match your search."


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

    assert main.summarize(result) == "Added your 10 best-matching jobs."


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


def test_stopping_a_run_marks_it_stopped_only_while_it_is_unfinished(monkeypatch: pytest.MonkeyPatch):
    db = FakeRest(run_status="running")
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    user = SimpleNamespace(id="user-1", access_token="token")

    assert main.stop_run("run-1", user, SimpleNamespace()) == {"status": "stopped"}
    [(table, filters, patch)] = db.updates
    assert table == "agent_runs" and filters == {"id": "eq.run-1", "status": "in.(queued,running)"}
    assert patch["status"] == "stopped" and patch["progress"] == "Stopped." and patch["finished_at"]

    with pytest.raises(HTTPException) as finished:
        main.stop_run("run-1", user, SimpleNamespace())
    assert finished.value.status_code == 409


def test_a_stopped_search_halts_at_its_next_progress_update_and_keeps_its_status(monkeypatch: pytest.MonkeyPatch):
    db = RunRest()
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    monkeypatch.setattr(main, "service_db", lambda settings: db)
    monkeypatch.setattr(main, "decrypt", lambda ciphertext, key: "key")
    reached: list[str] = []

    def search(**kwargs: Any) -> SearchResult:
        kwargs["report"]("Checking 5 companies…")
        db.run_status = "stopped"
        kwargs["report"]("Scoring 3 jobs…")
        reached.append("after stop")
        raise AssertionError("kept running after a stop")

    monkeypatch.setattr(main, "orchestrate_search", search)

    main.run_search("run-1", SearchRule(keywords=["engineer"]), SimpleNamespace(id="u", access_token="t"), SimpleNamespace(agent_encryption_key="k"))

    assert reached == [] and db.run_status == "stopped"
    final = db.updates[-1]
    assert final[1] == {"id": "eq.run-1"} and set(final[2]) == {"usage", "timings"}


def test_summary_mentions_the_min_score():
    kept = SearchResult(companies=4, found=300, matched=40, already_tracked=0, scored=20, failed=0, kept=3, min_score=70)
    none = SearchResult(companies=4, found=300, matched=40, already_tracked=0, scored=20, failed=0, kept=0, min_score=70)

    assert main.summarize(kept) == "Added 3 jobs scoring 70 or higher."
    assert main.summarize(none) == "No new jobs scored 70 or higher."


def test_admin_endpoints_refuse_users_without_the_admin_role():
    from app.auth import admin_user

    with pytest.raises(HTTPException) as refused:
        admin_user(SimpleNamespace(id="u", access_token="t", admin=False))
    assert refused.value.status_code == 403

    admin = SimpleNamespace(id="u", access_token="t", admin=True)
    assert admin_user(admin) is admin


class KeyRest:
    def __init__(self, personal: bool, shared: bool):
        self.personal, self.shared = personal, shared

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "api_credentials":
            return [{"ciphertext": "personal"}] if self.personal else []
        return [{"ciphertext": "shared"}] if self.shared else []


def test_runs_use_the_users_key_then_the_shared_key_then_the_setting(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "decrypt", lambda ciphertext, key: f"{ciphertext}-key")
    settings = SimpleNamespace(agent_encryption_key="k", anthropic_api_key="env-key")

    assert main.anthropic_key(KeyRest(personal=True, shared=True), "u", settings) == "personal-key"
    assert main.anthropic_key(KeyRest(personal=False, shared=True), "u", settings) == "shared-key"
    assert main.anthropic_key(KeyRest(personal=False, shared=False), "u", settings) == "env-key"


def test_call_stats_sum_up_each_step():
    def call(step: str, ms: int, error: str | None = None) -> dict[str, Any]:
        return {
            "step": step,
            "duration_ms": ms,
            "error": error,
            "input_tokens": 100,
            "output_tokens": 10,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 0,
            "web_search_requests": 0,
        }

    stats = main.call_stats([call("scoring", 900), call("scoring", 1200), call("scoring", 3000, "overloaded"), call("titles", 400)])

    scoring, titles = stats
    assert (scoring["step"], scoring["calls"], scoring["errors"], scoring["median_ms"], scoring["p95_ms"]) == ("scoring", 3, 1, 1200, 3000)
    assert (scoring["input_tokens"], scoring["cache_read_input_tokens"]) == (300, 150)
    assert (titles["calls"], titles["median_ms"]) == (1, 400)


def test_select_all_pages_past_the_row_limit():
    class Paged:
        def __init__(self):
            self.offsets: list[str] = []

        def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
            self.offsets.append(params["offset"])
            start = int(params["offset"])
            return [{"n": n} for n in range(start, min(start + int(params["limit"]), 5))]

    service = Paged()
    assert len(main.select_all(service, "llm_calls", {"order": "id"}, page=2)) == 5
    assert service.offsets == ["0", "2", "4"]


def test_vital_stats_give_the_median_and_75th_percentile_per_page_and_metric():
    rows = [{"page": "/tracker", "metric": "LCP", "value": v} for v in (800, 1200, 2000, 3500)]
    rows += [{"page": "/tracker", "metric": "TTFB", "value": 300}, {"page": "/jobs", "metric": "LCP", "value": 900}]

    stats = {(row["page"], row["metric"]): row for row in main.vital_stats(rows)}

    lcp = stats[("/tracker", "LCP")]
    assert (lcp["count"], lcp["median"], lcp["p75"]) == (4, 2000, 3500)
    assert main.vital_stats(rows)[0]["page"] == "/tracker"


def test_board_stats_sum_up_job_systems_and_list_the_slowest_boards():
    fetches = [
        {"board": "workday/acme", "source": "workday", "ms": 9000, "jobs": 1800, "outcome": "ok"},
        {"board": "workday/acme", "source": "workday", "ms": 11000, "jobs": 1850, "outcome": "ok"},
        {"board": "lever/beta", "source": "lever", "ms": 400, "jobs": 30, "outcome": "ok"},
        {"board": "lever/gone", "source": "lever", "ms": 200, "jobs": 0, "outcome": "gone"},
    ]

    stats = main.board_stats(fetches)

    workday, lever = stats["sources"]
    assert (workday["source"], workday["fetches"], workday["total_ms"], workday["jobs"]) == ("workday", 2, 20000, 1850)
    assert (lever["fetches"], lever["failures"]) == (2, 1)
    assert [row["board"] for row in stats["slowest"]] == ["workday/acme", "lever/beta", "lever/gone"]
    assert stats["slowest"][0]["median_ms"] == 11000


class RefreshRest:
    def __init__(self, recent: bool):
        self.recent = recent

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return [{"id": "refresh-1"}] if self.recent else []


def start_refresh(monkeypatch: pytest.MonkeyPatch, secret: str | None, authorization: str | None, recent: bool = False):
    monkeypatch.setattr(main, "service_db", lambda settings: RefreshRest(recent))
    background = BackgroundTasks()
    return main.start_refresh(SimpleNamespace(cron_secret=secret), background, authorization), background


def test_a_refresh_needs_the_cron_secret(monkeypatch: pytest.MonkeyPatch):
    for secret, authorization, status in ((None, "Bearer x", 503), ("a" * 32, None, 401), ("a" * 32, "Bearer wrong", 401)):
        with pytest.raises(HTTPException) as refused:
            start_refresh(monkeypatch, secret, authorization)
        assert refused.value.status_code == status


def test_a_refresh_is_refused_within_an_hour_of_the_last_one(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(HTTPException) as refused:
        start_refresh(monkeypatch, "a" * 32, f"Bearer {'a' * 32}", recent=True)

    assert refused.value.status_code == 409


def test_a_refresh_with_the_secret_starts_in_the_background(monkeypatch: pytest.MonkeyPatch):
    result, background = start_refresh(monkeypatch, "a" * 32, f"Bearer {'a' * 32}")

    assert result == {"status": "started"}
    [task] = background.tasks
    assert task.func is main.run_refresh


def test_refresh_board_rows_join_fetch_times_with_storage():
    refreshes = [
        {"board_fetches": [{"board": "ashby/acme", "ms": 300, "outcome": "ok"}, {"board": "lever/beta", "ms": 900, "outcome": "unreachable"}]},
        {"board_fetches": [{"board": "ashby/acme", "ms": 100, "outcome": "ok"}]},
    ]
    storage = [{"source": "ashby", "board": "acme", "jobs": 12, "open_jobs": 10, "bytes": 4096}]

    rows = main.refresh_board_rows(refreshes, storage)

    assert [row["board"] for row in rows] == ["lever/beta", "ashby/acme"]
    acme = rows[1]
    assert (acme["median_ms"], acme["last_ms"], acme["failures"]) == (300, 300, 0)
    assert (acme["open_jobs"], acme["saved_jobs"], acme["bytes"]) == (10, 12, 4096)
    assert (rows[0]["failures"], rows[0]["bytes"]) == (1, 0)


def test_a_finished_search_records_how_many_jobs_it_added(monkeypatch: pytest.MonkeyPatch):
    db = RunRest()
    monkeypatch.setattr(main, "user_db", lambda settings, token: db)
    monkeypatch.setattr(main, "service_db", lambda settings: db)
    monkeypatch.setattr(main, "decrypt", lambda ciphertext, key: "key")
    result = SearchResult(companies=4, found=300, matched=40, already_tracked=0, scored=20, failed=0, kept=10)
    monkeypatch.setattr(main, "orchestrate_search", lambda **kwargs: result)

    main.run_search("run-1", SearchRule(keywords=["engineer"]), SimpleNamespace(id="u", access_token="t"), SimpleNamespace(agent_encryption_key="k"))

    final = db.updates[-1][2]
    assert (final["status"], final["jobs_added"]) == ("done", 10)
