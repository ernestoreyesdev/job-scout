"""
Daily searches: each search a user marked runs again after the board refresh,
scoring its new matches, and the user gets one email listing the best
MAX_ALERT_JOBS new jobs across them that scored MIN_ALERT_SCORE or more. Each user's searches run in a short session
signed in as that user, so row-level security applies as in their own searches.
"""

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.agents.orchestrator import SearchResult, run_search
from app.agents.schemas import SearchRule
from app.config import Settings
from app.db import Rest, user_db
from app.mail import send_email
from app.telemetry import CallLog, RecordingClient

logger = logging.getLogger("agent")

MIN_ALERT_SCORE = 70
MAX_ALERT_JOBS = 10


@dataclass
class UserSession:
    """A session signed in as one user: their access token and sign-in email."""

    access_token: str
    email: str


def run_alerts(
    service: Rest,
    settings: Settings,
    client: Any,
    search: Callable[..., SearchResult] = run_search,
    open_session: Callable[[Settings, str], UserSession] | None = None,
    close_session: Callable[[Settings, UserSession], None] | None = None,
    as_user: Callable[[Settings, str], Rest] = user_db,
    send: Callable[..., bool] = send_email,
) -> dict[str, int]:
    """
    Runs every marked search for its user and emails each user their new strong
    matches. A user without a primary resume, or with a run already going, is
    skipped, and a user whose searches fail doesn't stop the others. Returns how
    many searches ran and how many emails went out.
    """
    alerts = service.select("search_alerts", {"select": "user_id,rule", "order": "created_at"})
    rules: dict[str, list[dict[str, Any]]] = {}
    for alert in alerts:
        rules.setdefault(alert["user_id"], []).append(alert["rule"])

    searches = emails = 0
    for user_id, user_rules in rules.items():
        resumes = service.select("resumes", {"select": "id,text", "user_id": f"eq.{user_id}", "is_primary": "eq.true"})
        if not resumes or not resumes[0]["text"]:
            logger.info("daily searches skipped: no resume", extra={"user_id": user_id})
            continue
        try:
            session = (open_session or sign_in_as)(settings, user_id)
        except Exception:
            logger.exception("daily searches skipped: couldn't sign in as the user", extra={"user_id": user_id})
            continue
        try:
            user = as_user(settings, session.access_token)
            started = datetime.now(UTC).isoformat()
            for rule in user_rules:
                if run_alert(user, service, settings, client, user_id, resumes[0], rule, search):
                    searches += 1
            jobs = keep_top(user, new_matches(user, started))
            key = f"matches/{user_id}/{started[:10]}"
            if jobs and send(settings, session.email, matches_subject(jobs), matches_body(settings, jobs), key):
                emails += 1
        finally:
            (close_session or sign_out)(settings, session)
    return {"searches": searches, "emails": emails}


def run_alert(
    user: Rest,
    service: Rest,
    settings: Settings,
    client: Any,
    user_id: str,
    resume: dict[str, Any],
    rule: dict[str, Any],
    search: Callable[..., SearchResult],
) -> bool:
    """
    Runs one marked search as a scored search keeping jobs at MIN_ALERT_SCORE or
    more, recorded in agent_runs like one the user started. Returns whether it ran.
    """
    body = SearchRule.model_validate({**rule, "score": True, "min_score": MIN_ALERT_SCORE, "web_lookup": False})
    try:
        [run] = user.insert(
            "agent_runs", {"user_id": user_id, "kind": "search", "input": body.model_dump(), "status": "running"}, select="id"
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 409:
            logger.info("daily search skipped: a run is already going", extra={"user_id": user_id})
            return False
        raise
    calls = CallLog(run["id"])
    outcome: dict[str, Any]
    try:
        result = search(
            rule=body,
            client=RecordingClient(client, calls),
            settings=settings,
            resume_id=resume["id"],
            resume_text=resume["text"],
            user_id=user_id,
            user=user,
            service=service,
            report=lambda _: None,
        )
        jobs = "job" if result.kept == 1 else "jobs"
        outcome = {
            "status": "done",
            "progress": f"Daily search: added {result.kept} {jobs} scoring {MIN_ALERT_SCORE} or higher.",
            "jobs_added": result.kept,
        }
    except Exception as error:
        logger.exception("daily search failed", extra={"user_id": user_id})
        outcome = {"status": "failed", "error": f"The daily search failed: {error}"}
    user.update(
        "agent_runs",
        {"id": f"eq.{run['id']}"},
        {**outcome, "usage": calls.usage().model_dump(), "finished_at": datetime.now(UTC).isoformat()},
    )
    calls.save(service)
    return outcome["status"] == "done"


def new_matches(user: Rest, since: str) -> list[dict[str, Any]]:
    """The user's Tracker jobs a search added since `since` that scored MIN_ALERT_SCORE or more, best first."""
    return user.select(
        "applications",
        {
            "select": "id,fit_score,posting:postings(title,company,location,url)",
            "added_by": "eq.search",
            "in_tracker": "eq.true",
            "fit_score": f"gte.{MIN_ALERT_SCORE}",
            "created_at": f"gte.{since}",
            "order": "fit_score.desc",
        },
    )


def sign_in_as(settings: Settings, user_id: str) -> UserSession:
    """
    A session for the user through Supabase Auth's admin API: a magic link token
    is generated and verified here, so no email is sent.
    """
    admin = {"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"}
    auth = f"{settings.supabase_url}/auth/v1"
    found = httpx.get(f"{auth}/admin/users/{user_id}", headers=admin, timeout=30)
    found.raise_for_status()
    email = found.json()["email"]
    link = httpx.post(f"{auth}/admin/generate_link", headers=admin, json={"type": "magiclink", "email": email}, timeout=30)
    link.raise_for_status()
    token_hash = link.json().get("hashed_token") or link.json()["properties"]["hashed_token"]
    session = httpx.post(
        f"{auth}/verify",
        headers={"apikey": settings.supabase_anon_key},
        json={"type": "magiclink", "token_hash": token_hash},
        timeout=30,
    )
    session.raise_for_status()
    return UserSession(session.json()["access_token"], email)


def sign_out(settings: Settings, session: UserSession) -> None:
    """Ends the session sign_in_as opened; a failure is logged, since the session expires on its own."""
    try:
        httpx.post(
            f"{settings.supabase_url}/auth/v1/logout",
            params={"scope": "local"},
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {session.access_token}"},
            timeout=30,
        ).raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("signing out of the daily search session failed: %s", error)


def matches_subject(jobs: list[dict[str, Any]]) -> str:
    count = len(jobs)
    return f"{count} new {'job' if count == 1 else 'jobs'} scoring {MIN_ALERT_SCORE}+ on Job Scout"


def matches_body(settings: Settings, jobs: list[dict[str, Any]]) -> str:
    """One line per job, linking to its posting, then a link to the Tracker."""
    items = "".join(
        f'<li><a href="{html.escape(job["posting"]["url"])}">{html.escape(job["posting"]["title"])}</a>'
        f" at {html.escape(job['posting']['company'])}"
        f"{f' ({html.escape(job["posting"]["location"])})' if job['posting'].get('location') else ''}"
        f": {job['fit_score']}</li>"
        for job in jobs
    )
    tracker = html.escape(f"{settings.app_url}/tracker")
    return (
        f"<p>Your daily searches found these new jobs:</p><ul>{items}</ul>"
        f'<p><a href="{tracker}">Open the Tracker</a> to rate them.</p>'
        "<p>Turn a daily search off under Recent searches on the Tracker.</p>"
    )


def keep_top(user: Rest, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keeps the first MAX_ALERT_JOBS of the day's matches on the Tracker and takes the rest off it, keeping their scores."""
    rest = [job["id"] for job in jobs[MAX_ALERT_JOBS:]]
    if rest:
        user.update("applications", {"id": f"in.({','.join(rest)})"}, {"in_tracker": False})
    return jobs[:MAX_ALERT_JOBS]
