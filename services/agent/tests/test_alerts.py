from typing import Any, cast

from app.agents import alerts
from app.agents.alerts import UserSession, matches_body, run_alerts
from app.agents.orchestrator import SearchResult
from app.config import Settings
from app.db import Rest
from tests.fakes import fake_settings

SETTINGS = fake_settings(app_url="https://scout.example")
MATCH = {"fit_score": 82, "posting": {"title": "Backend <Engineer>", "company": "Acme", "location": "Remote", "url": "https://jobs.example/1"}}


class FakeDb:
    """Rows a table returns, plus the writes made."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]]):
        self.tables = tables
        self.inserts: list[tuple[str, Any]] = []
        self.updates: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "resumes":
            return [row for row in self.tables.get(table, []) if params["user_id"] == f"eq.{row['user_id']}"]
        return self.tables.get(table, [])

    def insert(self, table: str, rows: Any, on_conflict: str | None = None, select: str | None = None) -> list[dict[str, Any]]:
        self.inserts.append((table, rows))
        return [{"id": f"run-{len(self.inserts)}"}]

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        self.updates.append((table, filters, patch))
        return []


def daily(service: FakeDb, users: dict[str, FakeDb], kept: int = 1) -> tuple[dict[str, int], list[dict[str, Any]], list[tuple]]:
    searches: list[dict[str, Any]] = []
    sent: list[tuple] = []

    def search(**kwargs: Any) -> SearchResult:
        searches.append(kwargs)
        return SearchResult(found=5, matched=3, scored=3, kept=kept)

    summary = run_alerts(
        cast(Rest, service),
        SETTINGS,
        client=None,
        search=search,
        open_session=lambda settings, user_id: UserSession(f"token-{user_id}", f"{user_id}@example.com"),
        close_session=lambda settings, session: None,
        as_user=lambda settings, token: cast(Rest, users[token]),
        send=lambda *args: sent.append(args) or True,
    )
    return summary, searches, sent


def test_marked_searches_run_as_their_user_with_a_minimum_of_70_and_email_the_new_matches():
    service = FakeDb(
        {
            "search_alerts": [{"user_id": "u1", "rule": {"keywords": ["backend engineer"], "limit": 5, "min_score": 50}}],
            "resumes": [{"user_id": "u1", "id": "resume-1", "text": "Engineer."}],
        }
    )
    user = FakeDb({"applications": [MATCH]})

    summary, searches, sent = daily(service, {"token-u1": user})

    assert summary == {"searches": 1, "emails": 1}
    [search] = searches
    assert search["user"] is user and search["user_id"] == "u1" and search["resume_id"] == "resume-1"
    assert (search["rule"].score, search["rule"].min_score, search["rule"].web_lookup) == (True, 70, False)
    [(table, run)] = user.inserts
    assert table == "agent_runs" and run["kind"] == "search" and run["input"]["min_score"] == 70
    assert user.updates[0][2]["status"] == "done"
    [(_, to, subject, _, key)] = sent
    assert to == "u1@example.com" and subject == "1 new job with a high matching score on Job Scout" and key.startswith("matches/u1/")


def test_no_email_goes_out_when_nothing_new_scored_70():
    service = FakeDb(
        {
            "search_alerts": [{"user_id": "u1", "rule": {"keywords": ["backend engineer"]}}],
            "resumes": [{"user_id": "u1", "id": "resume-1", "text": "Engineer."}],
        }
    )

    summary, _, sent = daily(service, {"token-u1": FakeDb({"applications": []})}, kept=0)

    assert summary == {"searches": 1, "emails": 0} and sent == []


def test_a_user_without_a_resume_is_skipped():
    service = FakeDb({"search_alerts": [{"user_id": "u1", "rule": {"keywords": ["designer"]}}], "resumes": []})

    summary, searches, sent = daily(service, {})

    assert summary == {"searches": 0, "emails": 0} and searches == [] and sent == []


def test_the_email_says_the_jobs_were_added_to_the_tracker_and_shows_each_one_escaped():
    body = matches_body(cast(Settings, SETTINGS), [MATCH])

    assert "1 new job with a high matching score was added to your Tracker." in body
    assert ">Backend &lt;Engineer&gt;</a>" in body and 'href="https://jobs.example/1"' in body
    assert "Acme · Remote" in body and ">82</div>" in body
    assert 'href="https://scout.example/tracker"' in body


def test_a_failed_search_is_recorded_and_the_email_still_covers_the_rest(monkeypatch):
    service = FakeDb(
        {
            "search_alerts": [{"user_id": "u1", "rule": {"keywords": ["a"]}}, {"user_id": "u1", "rule": {"keywords": ["b"]}}],
            "resumes": [{"user_id": "u1", "id": "resume-1", "text": "Engineer."}],
        }
    )
    user = FakeDb({"applications": [MATCH]})
    calls = iter([RuntimeError("boards down"), SearchResult(found=1, matched=1, scored=1, kept=1)])

    def search(**_: Any) -> SearchResult:
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(alerts.logger, "exception", lambda *a, **k: None)
    summary = run_alerts(
        cast(Rest, service),
        SETTINGS,
        client=None,
        search=search,
        open_session=lambda settings, user_id: UserSession("token", "u1@example.com"),
        close_session=lambda settings, session: None,
        as_user=lambda settings, token: cast(Rest, user),
        send=lambda *args: True,
    )

    assert summary == {"searches": 1, "emails": 1}
    assert [patch["status"] for _, _, patch in user.updates] == ["failed", "done"]


def test_only_the_best_10_matches_across_searches_stay_on_the_tracker_and_get_emailed():
    service = FakeDb(
        {
            "search_alerts": [{"user_id": "u1", "rule": {"keywords": ["a"]}}, {"user_id": "u1", "rule": {"keywords": ["b"]}}],
            "resumes": [{"user_id": "u1", "id": "resume-1", "text": "Engineer."}],
        }
    )
    matches = [{**MATCH, "id": f"app-{n}", "fit_score": 95 - n} for n in range(12)]
    user = FakeDb({"applications": matches})

    summary, _, sent = daily(service, {"token-u1": user})

    assert summary == {"searches": 2, "emails": 1}
    [(_, _, subject, body, _)] = sent
    assert subject == "10 new jobs with a high matching score on Job Scout" and ">86</div>" in body and ">85</div>" not in body
    [(_, filters, patch)] = [update for update in user.updates if update[0] == "applications"]
    assert filters == {"id": "in.(app-10,app-11)"} and patch == {"in_tracker": False}
