import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.agents.discovery.agent import discover_boards
from app.agents.schemas import SearchRule, Usage
from app.agents.scoring.agent import score_and_save
from app.config import Settings
from app.db import Rest
from app.sources import display_name, fetch_board, find_company
from app.sources.base import BoardNotFound, Posting, matches_keywords, matches_location, matches_workplace

logger = logging.getLogger("agent")

# Web discovery runs while the directory has fewer companies than this.
MIN_DIRECTORY = 25
# Jobs scored per company in a search across the directory.
MAX_PER_COMPANY = 3
FETCH_CONCURRENCY = 8

Board = tuple[str, str, str, str]


@dataclass
class SearchResult:
    companies: int
    found: int
    matched: int
    already_tracked: int
    scored: int
    failed: int


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
    finder: Callable[[str], list[Posting]] = find_company,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_board,
    discover: Callable[..., list[tuple[str, str]]] = discover_boards,
) -> SearchResult:
    """
    One search run: gathers open jobs from one company or the whole directory,
    filters them in code, then has the scoring agent score the newest ones the
    user hasn't tracked yet, up to the rule's limit.
    """
    if rule.company:
        report(f"Finding {rule.company}'s open jobs…")
        everything = finder(rule.company)
        if everything:
            first = everything[0]
            save_companies(
                service, [(first.source, first.board, first.company, "lookup")], {f"{first.source}/{first.board}": everything}
            )
        companies = 1
    else:
        everything, companies = directory_postings(rule, client, settings, user, service, usage, report, fetcher, discover)

    matched = [
        p
        for p in everything
        if matches_keywords(p, rule.keywords)
        and matches_workplace(p, rule.workplace_types)
        and matches_location(p, rule.location)
    ]
    if not matched:
        report(f"Found {len(everything)} open jobs, none match.")
        return SearchResult(companies, len(everything), 0, 0, 0, 0)

    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    matched = one_per_title(matched)
    rows = service.insert("postings", [p.model_dump(mode="json") for p in matched], on_conflict="source,external_id")
    ids = {(row["source"], row["external_id"]): row["id"] for row in rows}
    tracked = {row["posting_id"] for row in user.select("applications", {"select": "posting_id"})}
    fresh = [(ids[(p.source, p.external_id)], p) for p in matched if ids[(p.source, p.external_id)] not in tracked]
    todo = pick(fresh, rule.limit, None if rule.company else MAX_PER_COMPANY)
    already_tracked = len(matched) - len(fresh)
    report(
        f"Found {len(everything)} open jobs, {len(matched)} match, {already_tracked} already tracked. "
        f"Scoring {len(todo)}."
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
    return SearchResult(companies, len(everything), len(matched), already_tracked, scoring.scored, scoring.failed)


def directory_postings(
    rule: SearchRule,
    client: Any,
    settings: Settings,
    user: Rest,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    fetcher: Callable[[str, str, str], list[Posting]],
    discover: Callable[..., list[tuple[str, str]]],
) -> tuple[list[Posting], int]:
    """
    Open jobs at every directory company the user hasn't hidden, topping the
    directory up from the web while it's small.
    """
    directory = service.select("companies", {"select": "id,source,board,name,found_by"})
    hidden = {row["company_id"] for row in user.select("hidden_companies", {"select": "company_id"})}
    known = {(c["source"], c["board"]) for c in directory}
    boards: list[Board] = [(c["source"], c["board"], c["name"], c["found_by"]) for c in directory if c["id"] not in hidden]

    if len(directory) < MIN_DIRECTORY:
        report("Searching the web for companies that are hiring…")
        found = discover(client, settings.discovery_model, rule.keywords, rule.workplace_types, rule.location, usage)
        boards += [
            (source, board, display_name(board.replace("-", " ")), "discovery")
            for source, board in found
            if (source, board) not in known
        ]

    report(f"Checking {len(boards)} companies for open jobs…")
    lock = threading.Lock()
    fetched: dict[str, list[Posting]] = {}

    def fetch(entry: Board) -> None:
        source, board, name, _ = entry
        try:
            postings = fetcher(source, board, name)
        except BoardNotFound:
            return
        except Exception as error:
            logger.warning("fetching %s/%s failed: %s", source, board, error)
            return
        with lock:
            fetched[f"{source}/{board}"] = postings
            report(f"Checked {len(fetched)} of {len(boards)} companies…")

    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        list(pool.map(fetch, boards))

    live = [entry for entry in boards if f"{entry[0]}/{entry[1]}" in fetched]
    save_companies(service, live, {f"{source}/{board}": fetched[f"{source}/{board}"] for source, board, _, _ in live})
    return [p for postings in fetched.values() for p in postings], len(live)


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
