"""
Daily searches: each search a user marked runs again after the board refresh,
scoring its new matches, and ADMIN_EMAIL gets one email per user listing the
best MAX_ALERT_JOBS new jobs across them that scored MIN_ALERT_SCORE or more.
Each user's searches run in a short session signed in as that user, so
row-level security applies as in their own searches.
"""

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.agents.orchestrator import JobCache, SearchResult, run_search
from app.agents.schemas import SearchRule
from app.config import Settings
from app.constants import STRONG_FIT_SCORE
from app.db import HTTP, Conflict, Rest, check, user_db
from app.mail import send_email
from app.runs import record_run

logger = logging.getLogger("agent")

MIN_ALERT_SCORE = STRONG_FIT_SCORE
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
    Runs every marked search for its user and emails ADMIN_EMAIL each user's new
    strong matches; without ADMIN_EMAIL no email goes out. A user with daily
    emails off or without a primary resume, or with a run already going, is
    skipped, and a user whose searches fail doesn't stop the others. All searches
    share one JobCache, so saved jobs are read once. Returns how many searches
    ran and how many emails went out.
    """
    alerts = service.select("search_alerts", {"select": "user_id,rule", "order": "created_at"})
    switched_on = {row["user_id"] for row in service.select("profiles", {"select": "user_id", "daily_emails": "eq.true"})}
    rules: dict[str, list[dict[str, Any]]] = {}
    for alert in (alert for alert in alerts if alert["user_id"] in switched_on):
        rules.setdefault(alert["user_id"], []).append(alert["rule"])

    searches = emails = 0
    cache = JobCache()
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
            run_starts: list[str] = []
            for rule in user_rules:
                ran, run_started = run_alert(user, service, settings, client, user_id, resumes[0], rule, search, cache)
                searches += ran
                run_starts += [run_started] if run_started else []
            jobs = keep_top(user, new_matches(user, min(run_starts, default=started)))
            key = f"matches/{user_id}/{started[:10]}"
            if jobs and settings.admin_email and send(settings, settings.admin_email, matches_subject(jobs), matches_body(settings, jobs), key):
                emails += 1
        except Exception:
            logger.exception("daily searches failed for the user", extra={"user_id": user_id})
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
    cache: JobCache,
) -> tuple[bool, str | None]:
    """
    Runs one marked search as a scored search keeping jobs at MIN_ALERT_SCORE or
    more, recorded in agent_runs under the rule as the user marked it, like a
    search the user starts. Returns whether it finished, and when the database
    created its run row (None when it didn't start), which the email's window of
    new jobs starts from.
    """
    body = SearchRule.model_validate({**rule, "score": True, "min_score": MIN_ALERT_SCORE, "web_lookup": False})
    try:
        [run] = user.insert("agent_runs", {"user_id": user_id, "kind": "search", "input": rule}, select="id,created_at")
    except Conflict as error:
        if error.run_already_going:
            logger.info("daily search skipped: a run is already going", extra={"user_id": user_id})
            return False, None
        raise

    def work(client: Any, db: Rest, service: Rest, report: Callable[[str], None], timings: dict[str, int]) -> dict[str, Any]:
        result = search(
            rule=body,
            client=client,
            settings=settings,
            resume_id=resume["id"],
            resume_text=resume["text"],
            user_id=user_id,
            user=db,
            service=service,
            report=report,
            timings=timings,
            cache=cache,
        )
        jobs = "job" if result.kept == 1 else "jobs"
        return {
            "status": "done",
            "progress": f"Daily search: added {result.kept} {jobs} scoring {MIN_ALERT_SCORE} or higher.",
            "jobs_added": result.kept,
        }

    outcome = record_run(run["id"], "search", user, service, lambda: client, work)
    return outcome.get("status") == "done", run.get("created_at")


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
    found = HTTP.get(f"{auth}/admin/users/{user_id}", headers=admin)
    check(found)
    email = found.json()["email"]
    link = HTTP.post(f"{auth}/admin/generate_link", headers=admin, json={"type": "magiclink", "email": email})
    check(link)
    token_hash = link.json().get("hashed_token") or link.json()["properties"]["hashed_token"]
    session = HTTP.post(f"{auth}/verify", headers={"apikey": settings.supabase_anon_key}, json={"type": "magiclink", "token_hash": token_hash})
    check(session)
    return UserSession(session.json()["access_token"], email)


def sign_out(settings: Settings, session: UserSession) -> None:
    """Ends the session sign_in_as opened; a failure is logged, since the session expires on its own."""
    try:
        check(
            HTTP.post(
                f"{settings.supabase_url}/auth/v1/logout",
                params={"scope": "local"},
                headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {session.access_token}"},
            )
        )
    except httpx.HTTPError as error:
        logger.warning("signing out of the daily search session failed: %s", error)


def matches_subject(jobs: list[dict[str, Any]]) -> str:
    count = len(jobs)
    return f"{count} new {'job' if count == 1 else 'jobs'} with a high matching score on Job Scout"


def matches_body(settings: Settings, jobs: list[dict[str, Any]]) -> str:
    """A card per job with its score, linking to its posting, then a button to the Tracker, styled inline for email clients."""
    cards = "".join(match_card(job) for job in jobs)
    tracker = html.escape(f"{settings.app_url}/tracker")
    count = len(jobs)
    added = f"{count} new {'job' if count == 1 else 'jobs'} with a high matching score {'was' if count == 1 else 'were'} added to your Tracker."
    return (
        '<div style="background:#f4f4f5;padding:24px 12px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Arial,sans-serif;color:#18181b">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto">'
        '<tr><td style="padding:0 4px 16px;font-size:13px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;color:#71717a">Job Scout</td></tr>'
        '<tr><td style="background:#ffffff;border-radius:12px;padding:24px">'
        '<h1 style="margin:0 0 8px;font-size:20px;line-height:1.3">Your daily searches found new matches</h1>'
        f'<p style="margin:0 0 20px;font-size:15px;line-height:1.5;color:#52525b">{added}</p>'
        f"{cards}"
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 0"><tr>'
        f'<td style="background:#18181b;border-radius:8px"><a href="{tracker}" style="display:inline-block;padding:12px 20px;'
        'font-size:15px;font-weight:600;color:#fafafa;text-decoration:none">Rate them on the Tracker</a></td>'
        "</tr></table>"
        "</td></tr>"
        '<tr><td style="padding:16px 4px 0;font-size:12px;line-height:1.5;color:#71717a">'
        "Change your daily emails from the account menu on Job Scout.</td></tr>"
        "</table></div>"
    )


def keep_top(user: Rest, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keeps the first MAX_ALERT_JOBS of the day's matches on the Tracker and takes the rest off it, keeping their scores."""
    rest = [job["id"] for job in jobs[MAX_ALERT_JOBS:]]
    if rest:
        user.update("applications", {"id": f"in.({','.join(rest)})"}, {"in_tracker": False})
    return jobs[:MAX_ALERT_JOBS]


def match_card(job: dict[str, Any]) -> str:
    """One job as a row: its score in a green circle, then its linked title, company and location."""
    posting = job["posting"]
    place = f" · {html.escape(posting['location'])}" if posting.get("location") else ""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 12px;border:1px solid #e4e4e7;border-left:4px solid #10b981;border-radius:8px"><tr>'
        '<td width="64" style="padding:14px 0 14px 14px;vertical-align:middle;text-align:center">'
        '<div style="width:44px;height:44px;line-height:44px;border-radius:22px;background:#d1fae5;color:#065f46;'
        f'font-size:15px;font-weight:700;text-align:center">{job["fit_score"]}</div>'
        '<div style="margin-top:4px;font-size:11px;color:#71717a">Strong fit</div></td>'
        '<td style="padding:14px;vertical-align:middle">'
        f'<a href="{html.escape(posting["url"])}" style="font-size:16px;font-weight:600;color:#18181b;text-decoration:none">'
        f"{html.escape(posting['title'])}</a>"
        f'<div style="margin-top:4px;font-size:14px;color:#52525b">{html.escape(posting["company"])}{place}</div>'
        "</td></tr></table>"
    )
