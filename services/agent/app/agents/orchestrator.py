import logging
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import zip_longest
from typing import Any

from app.agents.discovery.agent import FoundBoard, discover_boards, find_company_boards, name_companies
from app.agents.triage.agent import shortlist
from app.agents.schemas import CompanyName, SearchRule, Usage
from app.agents.scoring.agent import score_and_save
from app.config import Settings
from app.db import Rest
from app.sources import careers_url, default_name, describe, display_name, fetch_board, find_company, is_complete
from app.sources.base import BoardNotFound, CompanyBoard, CompanyNotFound, Posting
from app.sources.filters import (
    matches_exclusions,
    matches_keywords,
    matches_location,
    matches_workplace,
    posted_within,
)

logger = logging.getLogger("agent")

# Web discovery runs while the directory has fewer companies than this, and otherwise once per interval.
MIN_DIRECTORY = 25
DISCOVERY_INTERVAL = timedelta(days=7)
# Boards from a company's web lookup checked before giving up.
MAX_LOOKUP_BOARDS = 5
# Matches per title shortlisting call, and calls per search; beyond that the newest matches are shortlisted.
MAX_TRIAGE = 300
MAX_TRIAGE_BATCHES = 10
# Company kinds left out of searches unless the user chose to show the company.
SKIPPED_KINDS = frozenset({"staffing", "aggregator"})
# Jobs scored per company in a search across the directory.
MAX_PER_COMPANY = 3
# A search scores this many times its job limit and keeps the best-scoring ones.
POOL_FACTOR = 2
FETCH_CONCURRENCY = 8
FETCH_RETRY_SECONDS = 2.0
# Consecutive searches that find a board gone before it leaves the directory.
MAX_MISSED_CHECKS = 3

Board = tuple[str, str, str, str]


@dataclass
class SearchResult:
    companies: int
    found: int
    matched: int
    already_tracked: int
    scored: int
    failed: int
    unreachable: int = 0
    company: str | None = None
    kept: int = 0


def run_search(
    *,
    rule: SearchRule,
    client: Any,
    settings: Settings,
    resume_id: str,
    resume_text: str,
    user_id: str,
    user: Rest,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    finder: Callable[[str], CompanyBoard] = find_company,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_board,
    discover: Callable[..., list[FoundBoard]] = discover_boards,
    describer: Callable[[Posting], str] = describe,
    lookup: Callable[..., list[FoundBoard]] = find_company_boards,
    namer: Callable[..., dict[tuple[str, str], CompanyName]] = name_companies,
    triage: Callable[..., list[int]] = shortlist,
) -> SearchResult:
    """
    One search run: gathers open jobs from one company or the whole directory,
    filters them in code, then has the scoring agent score the newest ones the
    user hasn't tracked yet, up to the rule's limit.
    """
    unreachable = 0
    if rule.company:
        report(f"Finding {rule.company}'s open jobs…")
        try:
            found = finder(rule.company)
        except CompanyNotFound:
            if not rule.web_lookup:
                raise
            report(f"Searching the web for {rule.company}'s job board…")
            found = web_lookup(rule.company, client, settings, usage, fetcher, lookup)
        save_companies(
            service, [(found.source, found.board, found.name, "lookup")], {f"{found.source}/{found.board}": found.postings}
        )
        label_if_new(found, client, settings, service, usage, namer)
        mark_closed(user, service, {f"{found.source}/{found.board}": found.postings})
        if not found.postings:
            report(f"Found {found.name}, but it has no open jobs listed.")
            return SearchResult(1, 0, 0, 0, 0, 0, company=found.name)
        everything = found.postings
        companies = 1
    else:
        everything, companies, unreachable = directory_postings(
            rule, client, settings, user, service, usage, report, fetcher, discover, namer
        )

    matched = [
        p
        for p in everything
        if matches_keywords(p, rule.keywords)
        and matches_exclusions(p, rule.exclude)
        and matches_workplace(p, rule.workplace_types)
        and matches_location(p, rule.location)
        and posted_within(p, rule.posted_within_days)
    ]
    if not matched:
        report(f"Found {len(everything)} open jobs, none match.")
        return SearchResult(companies, len(everything), 0, 0, 0, 0, unreachable)

    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    matched = one_per_title(matched)
    rows = service.insert("postings", [p.model_dump(mode="json") for p in matched], on_conflict="source,external_id")
    ids = {(row["source"], row["external_id"]): row["id"] for row in rows}
    tracked = {row["posting_id"] for row in user.select("applications", {"select": "posting_id"})}
    fresh = [(ids[(p.source, p.external_id)], p) for p in matched if ids[(p.source, p.external_id)] not in tracked]
    pool_size = rule.limit * POOL_FACTOR
    per_company = None if rule.company else MAX_PER_COMPANY
    if len(fresh) > pool_size:
        report(f"Shortlisting {min(len(fresh), MAX_TRIAGE * MAX_TRIAGE_BATCHES)} of {len(fresh)} matches by title…")
        fresh = by_title_fit(fresh, pool_size, client, settings, resume_text, usage, triage)
    pool = pick(fresh, pool_size, per_company)
    todo = with_descriptions(pool, service, describer)
    already_tracked = len(matched) - len(fresh)
    report(
        f"Found {len(everything)} open jobs, {len(matched)} match, {already_tracked} already tracked. "
        f"Scoring {len(todo)} to keep the best {min(rule.limit, len(todo))}."
    )

    scoring = score_and_save(
        client=client,
        model=settings.scoring_model,
        effort=settings.scoring_effort,
        todo=todo,
        resume_id=resume_id,
        resume_text=resume_text,
        user_id=user_id,
        user=user,
        usage=usage,
        report=report,
    )
    kept = keep_best(user, todo, scoring.scores, rule.limit)
    return SearchResult(
        companies,
        len(everything),
        len(matched),
        already_tracked,
        scoring.scored,
        scoring.failed,
        unreachable,
        kept=kept,
    )


def directory_postings(
    rule: SearchRule,
    client: Any,
    settings: Settings,
    user: Rest,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    fetcher: Callable[[str, str, str], list[Posting]],
    discover: Callable[..., list[FoundBoard]],
    namer: Callable[..., dict[tuple[str, str], CompanyName]],
) -> tuple[list[Posting], int, int]:
    """
    Open jobs at every directory company the user hasn't hidden, topping the
    directory up from the web while it's small or once a week. Staffing agencies
    and aggregators count as hidden unless the user chose to show them. Returns
    the jobs, the companies checked and the companies that couldn't be reached.
    """
    directory = service.select("companies", {"select": "id,source,board,name,found_by,missed_checks,kind"})
    choices = {row["company_id"]: row["hidden"] for row in user.select("hidden_companies", {"select": "company_id,hidden"})}
    known = {(c["source"], c["board"]) for c in directory}
    boards: list[Board] = [
        (c["source"], c["board"], c["name"], c["found_by"])
        for c in directory
        if not choices.get(c["id"], c["kind"] in SKIPPED_KINDS)
    ]
    skipped: set[str] = set()
    kinds: dict[tuple[str, str], str] = {}

    if len(directory) < MIN_DIRECTORY or discovery_due(service):
        report("Searching the web for companies that are hiring…")
        found = discover(client, settings.discovery_model, rule.keywords, rule.workplace_types, rule.location, usage)
        new = [b for b in found if (b.source, b.board) not in known]
        named = namer(client, settings.discovery_model, new, usage) if new else {}
        kinds = {key: entry.kind for key, entry in named.items()}
        boards += [
            (
                b.source,
                b.board,
                named[(b.source, b.board)].name if (b.source, b.board) in named else default_name(b.source, b.board),
                "discovery",
            )
            for b in new
        ]
        skipped = {f"{source}/{board}" for (source, board), kind in kinds.items() if kind in SKIPPED_KINDS}
        service.insert(
            "directory_discoveries",
            {"keywords": rule.keywords, "boards_found": len(found), "boards_added": len(new)},
        )

    report(f"Checking {len(boards)} companies for open jobs…")
    lock = threading.Lock()
    fetched: dict[str, list[Posting]] = {}
    gone: list[str] = []
    unreachable: list[str] = []

    def fetch(entry: Board) -> None:
        source, board, name, _ = entry
        key = f"{source}/{board}"
        for attempt in range(2):
            try:
                postings = fetcher(source, board, name)
                break
            except BoardNotFound:
                with lock:
                    gone.append(key)
                return
            except Exception as error:
                logger.warning("fetching %s failed (attempt %d): %s", key, attempt + 1, error)
                if attempt == 0:
                    time.sleep(FETCH_RETRY_SECONDS)
        else:
            with lock:
                unreachable.append(key)
            return
        with lock:
            fetched[key] = postings
            report(f"Checked {len(fetched)} of {len(boards)} companies…")

    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        list(pool.map(fetch, boards))

    live = [entry for entry in boards if f"{entry[0]}/{entry[1]}" in fetched]
    save_companies(service, live, fetched)
    if kinds:
        record_kinds(service, {key: kind for key, kind in kinds.items() if f"{key[0]}/{key[1]}" in fetched})
    record_misses(service, [c for c in directory if f"{c['source']}/{c['board']}" in gone])
    mark_closed(user, service, fetched)
    if unreachable:
        report(f"Couldn't reach {len(unreachable)} of {len(boards)} companies; skipped them this time.")
    searched = [entry for entry in live if f"{entry[0]}/{entry[1]}" not in skipped]
    postings = [p for key, found in fetched.items() if key not in skipped for p in found]
    return postings, len(searched), len(unreachable)


def save_companies(service: Rest, boards: list[Board], postings: dict[str, list[Posting]]) -> None:
    """Records each confirmed board in the directory with its open job count."""
    if not boards:
        return
    now = datetime.now(UTC).isoformat()
    rows = []
    for source, board, name, found_by in boards:
        jobs = postings.get(f"{source}/{board}", [])
        rows.append(
            {
                "source": source,
                "board": board,
                "name": jobs[0].company if jobs else name,
                "open_jobs": len(jobs),
                "found_by": found_by,
                "checked_at": now,
                "missed_checks": 0,
                "careers_url": careers_url(source, board),
            }
        )
    service.insert("companies", rows, on_conflict="source,board")


def one_per_title(postings: list[Posting]) -> list[Posting]:
    """First posting of each title at each company; the same role listed per country or city counts once."""
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for p in postings:
        key = (p.source, p.board, " ".join(p.title.lower().split()))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def pick(fresh: list[tuple[str, Posting]], limit: int, per_company: int | None) -> list[tuple[str, Posting]]:
    """Up to `limit` jobs in order, at most `per_company` from any one company when set."""
    counts: dict[tuple[str, str], int] = {}
    chosen = []
    for posting_id, p in fresh:
        if len(chosen) == limit:
            break
        company = (p.source, p.board)
        if per_company is not None and counts.get(company, 0) >= per_company:
            continue
        counts[company] = counts.get(company, 0) + 1
        chosen.append((posting_id, p))
    return chosen


def record_misses(service: Rest, companies: list[dict[str, Any]]) -> None:
    """Counts a miss for each directory company whose board is gone, removing it at MAX_MISSED_CHECKS."""
    for company in companies:
        misses = company["missed_checks"] + 1
        if misses >= MAX_MISSED_CHECKS:
            service.delete("companies", {"id": f"eq.{company['id']}"})
        else:
            service.update("companies", {"id": f"eq.{company['id']}"}, {"missed_checks": misses})


def with_descriptions(
    todo: list[tuple[str, Posting]], service: Rest, describer: Callable[[Posting], str]
) -> list[tuple[str, Posting]]:
    """
    Fills in descriptions that a system's job list left out and saves them.
    A job whose description can't be fetched is dropped rather than scored blind.
    """
    ready: list[tuple[str, Posting]] = []
    described: list[Posting] = []
    for posting_id, posting in todo:
        if posting.description:
            ready.append((posting_id, posting))
            continue
        try:
            full = posting.model_copy(update={"description": describer(posting)})
        except Exception as error:
            logger.warning("describing %s/%s failed: %s", posting.source, posting.external_id, error)
            continue
        ready.append((posting_id, full))
        described.append(full)
    if described:
        service.insert("postings", [p.model_dump(mode="json") for p in described], on_conflict="source,external_id")
    return ready


def discovery_due(service: Rest) -> bool:
    """True when web discovery hasn't run within DISCOVERY_INTERVAL."""
    cutoff = (datetime.now(UTC) - DISCOVERY_INTERVAL).isoformat()
    recent = service.select("directory_discoveries", {"select": "id", "ran_at": f"gte.{cutoff}", "limit": "1"})
    return not recent


def web_lookup(
    company: str,
    client: Any,
    settings: Settings,
    usage: Usage,
    fetcher: Callable[[str, str, str], list[Posting]],
    lookup: Callable[..., list[FoundBoard]],
) -> CompanyBoard:
    """
    Finds a company's board through a web search when no spelling of its name
    matched. A board counts only when its name or its jobs' company name
    contains the company's name; the one with the most postings wins.
    """
    wanted = compact(company)
    found = lookup(client, settings.discovery_model, company, usage)
    ordered = sorted(found, key=lambda b: wanted not in compact(b.board))[:MAX_LOOKUP_BOARDS]

    name = display_name(company)
    best: CompanyBoard | None = None
    for b in ordered:
        try:
            postings = fetcher(b.source, b.board, name)
        except Exception as error:
            logger.warning("lookup of %s on %s/%s failed: %s", company, b.source, b.board, error)
            continue
        named = wanted in compact(b.board) or any(wanted in compact(p.company) for p in postings[:1])
        if named and (best is None or len(postings) > len(best.postings)):
            best = CompanyBoard(b.source, b.board, name, postings)
    if best is None:
        raise CompanyNotFound(f"Couldn't find job listings for {company}, even with a web search.")
    return best


def compact(text: str) -> str:
    """Lowercase letters and digits only: 'CVS Health' -> 'cvshealth'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def keep_best(user: Rest, todo: list[tuple[str, Posting]], scores: dict[str, int], limit: int) -> int:
    """
    Keeps the `limit` highest-scoring jobs on the Tracker (ties go to the newer
    job) and takes the rest off it. Their scores stay saved, so later searches
    skip them instead of scoring them again. Returns how many were kept.
    """
    order = {posting_id: i for i, (posting_id, _) in enumerate(todo)}
    ranked = sorted(scores, key=lambda posting_id: (-scores[posting_id], order.get(posting_id, len(order))))
    rest = ranked[limit:]
    if rest:
        user.update("applications", {"posting_id": f"in.({','.join(rest)})"}, {"in_tracker": False})
    return len(ranked) - len(rest)


def record_kinds(service: Rest, kinds: dict[tuple[str, str], str]) -> None:
    """Saves the kind (employer, staffing, aggregator) labeled for newly discovered companies."""
    for (source, board), kind in kinds.items():
        service.update("companies", {"source": f"eq.{source}", "board": f"eq.{board}"}, {"kind": kind})


def by_title_fit(
    fresh: list[tuple[str, Posting]],
    count: int,
    client: Any,
    settings: Settings,
    resume_text: str,
    usage: Usage,
    triage: Callable[..., list[int]],
) -> list[tuple[str, Posting]]:
    """
    Reorders unscored matches by how well their titles fit the resume, best
    first. Up to MAX_TRIAGE_BATCHES batches of MAX_TRIAGE titles are shortlisted
    in parallel, then one more call ranks the batches' picks together. Each call
    asks for twice `count` so the per-company cap still leaves a full pool.
    """
    want = count * 2

    def rank(candidates: list[tuple[str, Posting]], spent: Usage) -> list[tuple[str, Posting]]:
        picked = triage(client, settings.scoring_model, resume_text, [p for _, p in candidates], want, spent)
        return [candidates[i] for i in picked]

    batches = [fresh[i : i + MAX_TRIAGE] for i in range(0, min(len(fresh), MAX_TRIAGE * MAX_TRIAGE_BATCHES), MAX_TRIAGE)]
    if len(batches) == 1:
        return rank(batches[0], usage)

    spent = [Usage() for _ in batches]
    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        picks = list(pool.map(rank, batches, spent))
    for batch_usage in spent:
        usage.add(batch_usage)
    # Interleaved so each batch's best picks come first when the finalists are trimmed.
    finalists = [pick for rank_picks in zip_longest(*picks) for pick in rank_picks if pick is not None]
    return rank(finalists[:MAX_TRIAGE], usage)


def label_if_new(
    found: CompanyBoard,
    client: Any,
    settings: Settings,
    service: Rest,
    usage: Usage,
    namer: Callable[..., dict[tuple[str, str], CompanyName]],
) -> None:
    """Labels a company found by name the first time it's found; its name stays the one its board gave."""
    rows = service.select(
        "companies", {"select": "kind", "source": f"eq.{found.source}", "board": f"eq.{found.board}"}
    )
    if rows and rows[0].get("kind"):
        return
    named = namer(client, settings.discovery_model, [FoundBoard(found.source, found.board, [found.name])], usage)
    if (found.source, found.board) in named:
        record_kinds(service, {(found.source, found.board): named[(found.source, found.board)].kind})


def rescore(
    *,
    client: Any,
    settings: Settings,
    resume_id: str,
    resume_text: str,
    user_id: str,
    user: Rest,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    describer: Callable[[Posting], str] = describe,
) -> int:
    """
    Re-scores the jobs on the user's Tracker or Jobs that were scored against
    another resume. Their status, notes and place on the Tracker stay as they
    are. Returns how many were re-scored.
    """
    rows = user.select(
        "applications",
        {
            "select": "posting_id,posting:postings(*)",
            "resume_id": f"neq.{resume_id}",
            "or": "(in_tracker.eq.true,status.neq.new)",
        },
    )
    todo = [(row["posting_id"], Posting.model_validate(row["posting"])) for row in rows]
    if not todo:
        report("Every job is already scored with your current resume.")
        return 0
    report(f"Re-scoring {len(todo)} {'job' if len(todo) == 1 else 'jobs'} with your current resume…")
    scoring = score_and_save(
        client=client,
        model=settings.scoring_model,
        effort=settings.scoring_effort,
        todo=with_descriptions(todo, service, describer),
        resume_id=resume_id,
        resume_text=resume_text,
        user_id=user_id,
        user=user,
        usage=usage,
        report=report,
    )
    return scoring.scored


def mark_closed(user: Rest, service: Rest, fetched: dict[str, list[Posting]]) -> None:
    """
    Marks the user's tracked postings closed when a complete fetch of their
    board no longer lists them, and open again when it lists them again.
    Boards cut off at their system's limit are skipped.
    """
    listed = {
        key: {p.external_id for p in postings}
        for key, postings in fetched.items()
        if is_complete(key.split("/", 1)[0], postings)
    }
    if not listed:
        return
    rows = user.select("applications", {"select": "posting:postings(id,source,board,external_id,closed_at)"})
    closing, reopening = [], []
    for row in rows:
        posting = row["posting"]
        ids = listed.get(f"{posting['source']}/{posting['board']}")
        if ids is None:
            continue
        if posting["external_id"] not in ids and posting["closed_at"] is None:
            closing.append(posting["id"])
        elif posting["external_id"] in ids and posting["closed_at"] is not None:
            reopening.append(posting["id"])
    if closing:
        service.update("postings", {"id": f"in.({','.join(closing)})"}, {"closed_at": datetime.now(UTC).isoformat()})
    if reopening:
        service.update("postings", {"id": f"in.({','.join(reopening)})"}, {"closed_at": None})
