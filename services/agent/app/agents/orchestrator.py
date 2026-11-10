import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import zip_longest
from typing import Any


from app.agents.discovery.agent import FoundBoard, discover_boards, find_company_boards, name_companies
from app.agents.hiring_threads.agent import HiringPost, extract_jobs, recent_posts
from app.agents.triage.agent import shortlist
from app.agents.titles.agent import related_titles
from app.agents.schemas import CompanyName, SearchRule, Usage
from app.agents.scoring.agent import score_and_save
from app.agents.scoring.prompts import LabeledJob
from app.config import Settings
from app.db import Rest
from app.sources import (
    board_from_url,
    careers_url,
    default_name,
    describe,
    display_name,
    fetch_board,
    find_company,
    is_complete,
)
from app.sources.base import BoardNotFound, CompanyBoard, CompanyNotFound, Posting
from app.telemetry import ContextThreadPool, timed
from app.sources.filters import (
    matches_exclusions,
    matches_keywords,
    matches_location,
    matches_workplace,
    posted_within,
)

logger = logging.getLogger("agent")

# Web discovery runs while the directory has fewer companies than this, for keyword sets it hasn't run for, and otherwise once per interval.
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
# Most recent jobs per label shown to scoring, and how many of each label it takes before any are shown.
MAX_EXAMPLES = 15
MIN_EXAMPLES = 3

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
    min_score: int | None = None
    unreachable_boards: list[str] = field(default_factory=list)
    board_fetches: list[dict[str, Any]] = field(default_factory=list)


def run_search(
    *,
    rule: SearchRule,
    client: Any,
    settings: Settings,
    resume_id: str | None,
    resume_text: str | None,
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
    read_posts: Callable[[], list[HiringPost]] = recent_posts,
    extractor: Callable[..., list[Posting]] = extract_jobs,
    expander: Callable[..., list[str]] = related_titles,
    timings: dict[str, int] | None = None,
) -> SearchResult:
    """
    One search run: gathers open jobs from one company, or from the whole
    directory plus recent Hacker News hiring posts, filters them in code against
    the keywords and the related titles Claude lists for them, then has the scoring agent score the newest ones the
    user hasn't tracked yet, up to the rule's limit. Without rule.score, the newest
    of those are added unscored instead. Milliseconds per step go into timings when given.
    """
    unreachable: list[str] = []
    fetches: list[dict[str, Any]] = []
    if rule.company:
        with timed(timings, "companies"):
            report("Gathering open jobs…")
            try:
                found = finder(rule.company)
            except CompanyNotFound:
                if not rule.web_lookup:
                    raise
                report("Gathering open jobs…")
                found = web_lookup(rule.company, client, settings, usage, fetcher, lookup)
            save_companies(
                service, [(found.source, found.board, found.name, "lookup")], {f"{found.source}/{found.board}": found.postings}
            )
            label_if_new(found, client, settings, service, usage, namer)
            remove_duplicate_names(service)
            mark_closed(user, service, {f"{found.source}/{found.board}": found.postings})
        if not found.postings:
            report(f"Found {found.name}, but it has no open jobs listed.")
            return SearchResult(1, 0, 0, 0, 0, 0, company=found.name)
        everything = found.postings
        companies = 1
    else:
        with timed(timings, "companies"):
            everything, companies, unreachable, fetches = directory_postings(
                rule, client, settings, user, service, usage, report, fetcher, discover, namer
            )
        with timed(timings, "hacker_news"):
            everything += hiring_thread_postings(client, settings, service, usage, report, read_posts, extractor)

    with timed(timings, "titles"):
        titles = expander(client, settings.discovery_model, rule.keywords, usage) if everything else []
    if titles:
        logger.info("related titles", extra={"keywords": rule.keywords, "titles": titles})
    report("Matching jobs to your search…")
    keywords = [*rule.keywords, *titles]
    matched = [
        p
        for p in everything
        if matches_keywords(p, keywords)
        and matches_exclusions(p, rule.exclude)
        and matches_workplace(p, rule.workplace_types)
        and matches_location(p, rule.location)
        and posted_within(p, rule.posted_within_days)
    ]
    if not matched:
        report("No jobs match your search.")
        return SearchResult(
            companies,
            len(everything),
            0,
            0,
            0,
            0,
            len(unreachable),
            unreachable_boards=unreachable,
            board_fetches=fetches,
        )

    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    matched = one_per_job(one_per_title(matched))
    rows = service.insert("postings", [p.model_dump(mode="json") for p in matched], on_conflict="source,external_id")
    ids = {(row["source"], row["external_id"]): row["id"] for row in rows}
    tracked = {row["posting_id"] for row in user.select("applications", {"select": "posting_id"})}
    fresh = [(ids[(p.source, p.external_id)], p) for p in matched if ids[(p.source, p.external_id)] not in tracked]
    per_company = None if rule.company else MAX_PER_COMPANY
    already_tracked = len(matched) - len(fresh)
    if not rule.score:
        newest = pick(fresh, rule.limit, per_company)
        report("Adding the newest matches…")
        if newest:
            user.insert(
                "applications",
                [{"user_id": user_id, "posting_id": posting_id} for posting_id, _ in newest],
                on_conflict="user_id,posting_id",
            )
        return SearchResult(
            companies,
            len(everything),
            len(matched),
            already_tracked,
            0,
            0,
            len(unreachable),
            kept=len(newest),
            unreachable_boards=unreachable,
            board_fetches=fetches,
        )

    pool_size = rule.limit * POOL_FACTOR
    if len(fresh) > pool_size:
        report("Matching jobs to your search…")
        with timed(timings, "shortlist"):
            fresh = by_title_fit(fresh, pool_size, client, settings, resume_text, usage, triage)
    pool = pick(fresh, pool_size, per_company)
    todo = with_descriptions(pool, service, describer)
    report("Scoring jobs against your resume…")

    with timed(timings, "scoring"):
        scoring = score_and_save(
            client=client,
            model=settings.scoring_model,
            effort=settings.scoring_effort,
            todo=todo,
            resume_id=resume_id,
            resume_text=resume_text,
            user_id=user_id,
            user=user,
            service=service,
            usage=usage,
            report=report,
            examples=labeled_examples(user),
        )
    kept = keep_best(user, todo, scoring.scores, rule.limit, rule.min_score)
    return SearchResult(
        companies,
        len(everything),
        len(matched),
        already_tracked,
        scoring.scored,
        scoring.failed,
        len(unreachable),
        kept=kept,
        min_score=rule.min_score,
        unreachable_boards=unreachable,
        board_fetches=fetches,
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
    the jobs, the companies checked, the boards ("source/board") that couldn't
    be reached, and how long each board's fetch took and how it ended.
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

    if len(directory) < MIN_DIRECTORY or discovery_due(service, rule.keywords):
        report("Gathering open jobs…")
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

    report("Gathering open jobs…")
    lock = threading.Lock()
    fetched: dict[str, list[Posting]] = {}
    gone: list[str] = []
    unreachable: list[str] = []
    fetches: list[dict[str, Any]] = []

    def fetch(entry: Board) -> None:
        source, board, name, _ = entry
        key = f"{source}/{board}"
        started = time.monotonic()

        def record(outcome: str, jobs: int = 0) -> None:
            ms = round((time.monotonic() - started) * 1000)
            fetches.append({"board": key, "source": source, "ms": ms, "jobs": jobs, "outcome": outcome})

        for attempt in range(2):
            try:
                postings = fetcher(source, board, name)
                break
            except BoardNotFound:
                with lock:
                    gone.append(key)
                    record("gone")
                return
            except Exception as error:
                logger.warning("fetching %s failed (attempt %d): %s", key, attempt + 1, error, extra={"board": key})
                if attempt == 0:
                    time.sleep(FETCH_RETRY_SECONDS)
        else:
            with lock:
                unreachable.append(key)
                record("unreachable")
            return
        with lock:
            fetched[key] = postings
            record("ok", len(postings))
            report("Gathering open jobs…")

    with ContextThreadPool(max_workers=FETCH_CONCURRENCY) as pool:
        list(pool.map(fetch, boards))

    live = [entry for entry in boards if f"{entry[0]}/{entry[1]}" in fetched]
    save_companies(service, live, fetched)
    if any(entry[3] == "discovery" and (entry[0], entry[1]) not in known for entry in live):
        remove_duplicate_names(service)
    if kinds:
        record_kinds(service, {key: kind for key, kind in kinds.items() if f"{key[0]}/{key[1]}" in fetched})
    record_misses(service, [c for c in directory if f"{c['source']}/{c['board']}" in gone])
    mark_closed(user, service, fetched)
    searched = [entry for entry in live if f"{entry[0]}/{entry[1]}" not in skipped]
    postings = [p for key, found in fetched.items() if key not in skipped for p in found]
    return postings, len(searched), sorted(unreachable), fetches


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


def discovery_due(service: Rest, keywords: list[str]) -> bool:
    """True when web discovery hasn't run within DISCOVERY_INTERVAL or has never run for this keyword set."""
    cutoff = (datetime.now(UTC) - DISCOVERY_INTERVAL).isoformat()
    if not service.select("directory_discoveries", {"select": "id", "ran_at": f"gte.{cutoff}", "limit": "1"}):
        return True
    wanted = keyword_set(keywords)
    return all(keyword_set(row["keywords"]) != wanted for row in service.select("directory_discoveries", {"select": "keywords"}))


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


def keep_best(
    user: Rest, todo: list[tuple[str, Posting]], scores: dict[str, int], limit: int, min_score: int | None = None
) -> int:
    """
    Keeps the `limit` highest-scoring jobs at or above `min_score` on the Tracker
    (ties go to the newer job) and takes the rest off it. Their scores stay
    saved, so later searches skip them instead of scoring them again. Returns
    how many were kept.
    """
    undated = datetime.min.replace(tzinfo=UTC)
    posted = {posting_id: p.posted_at or undated for posting_id, p in todo}
    ranked = sorted(scores, key=lambda posting_id: (scores[posting_id], posted.get(posting_id, undated)), reverse=True)
    eligible = [posting_id for posting_id in ranked if min_score is None or scores[posting_id] >= min_score]
    kept = set(eligible[:limit])
    rest = [posting_id for posting_id in ranked if posting_id not in kept]
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
    with ContextThreadPool(max_workers=len(batches)) as pool:
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
    timings: dict[str, int] | None = None,
) -> int:
    """
    Scores the jobs on the user's Tracker or Jobs that were scored against
    another resume or not scored at all. Their status, notes and place on the Tracker stay as they
    are. Returns how many were re-scored.
    """
    rows = user.select(
        "applications",
        {
            "select": "posting_id,posting:postings(*)",
            "and": f"(or(resume_id.is.null,resume_id.neq.{resume_id}),or(in_tracker.eq.true,status.neq.new))",
        },
    )
    todo = [(row["posting_id"], Posting.model_validate(row["posting"])) for row in rows]
    if not todo:
        report("Every job is already scored with your current resume.")
        return 0
    report("Scoring jobs against your resume…")
    with timed(timings, "scoring"):
        scoring = score_and_save(
            client=client,
            model=settings.scoring_model,
            effort=settings.scoring_effort,
            todo=with_descriptions(todo, service, describer),
            resume_id=resume_id,
            resume_text=resume_text,
            user_id=user_id,
            user=user,
            service=service,
            usage=usage,
            report=report,
            examples=labeled_examples(user),
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


def keyword_set(keywords: list[str]) -> frozenset[str]:
    """Keywords compared without case, spacing or order: ['AI  Engineer'] equals ['ai engineer']."""
    return frozenset(" ".join(keyword.lower().split()) for keyword in keywords)


@dataclass
class ImportResult:
    added: list[str]
    existing: int
    not_found: list[str]
    empty: list[str]


def import_companies(
    *,
    entries: list[str],
    client: Any,
    settings: Settings,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    finder: Callable[[str], CompanyBoard] = find_company,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_board,
    namer: Callable[..., dict[tuple[str, str], CompanyName]] = name_companies,
) -> ImportResult:
    """
    Adds companies to the directory from careers page URLs or company names.
    Names are tried on every system's spellings; URLs are read on the system
    they belong to, after one call names and labels every new company, so
    their jobs carry the company's real name.
    """
    known = {(c["source"], c["board"]) for c in service.select("companies", {"select": "source,board"})}
    lock = threading.Lock()
    by_name: dict[tuple[str, str], tuple[str, CompanyBoard]] = {}
    by_url: dict[tuple[str, str], str] = {}
    not_found: list[str] = []

    def look_up(entry: str) -> None:
        try:
            result = finder(entry)
        except CompanyNotFound:
            result = None
        except Exception as error:
            logger.warning("importing %s failed: %s", entry, error)
            result = None
        with lock:
            if result is None:
                not_found.append(entry)
            else:
                by_name.setdefault((result.source, result.board), (entry, result))
            report(f"Looked up {len(by_name) + len(not_found)} of {len(entries)}…")

    names = []
    for entry in entries:
        if not entry.startswith(("http://", "https://")):
            names.append(entry)
        elif (board := board_from_url(entry)) is None:
            not_found.append(entry)
        else:
            by_url.setdefault(board, entry)
    with ContextThreadPool(max_workers=FETCH_CONCURRENCY) as pool:
        list(pool.map(look_up, names))

    existing = {key for key in [*by_name, *by_url] if key in known}
    new_names = {key: value for key, value in by_name.items() if key not in known}
    new_urls = {key: url for key, url in by_url.items() if key not in known and key not in by_name}
    candidates = [FoundBoard(r.source, r.board, [entry, *(p.title for p in r.postings[:3])]) for entry, r in new_names.values()]
    candidates += [FoundBoard(source, board, [url]) for (source, board), url in new_urls.items()]
    named = namer(client, settings.discovery_model, candidates, usage) if candidates else {}

    fetched = {f"{r.source}/{r.board}": r.postings for _, r in new_names.values()}
    boards: list[Board] = [(r.source, r.board, r.name, "import") for _, r in new_names.values()]

    def fetch(key: tuple[str, str]) -> None:
        source, board = key
        name = named[key].name if key in named else default_name(source, board)
        try:
            postings = fetcher(source, board, name)
        except Exception as error:
            logger.warning("importing %s failed: %s", new_urls[key], error)
            with lock:
                not_found.append(new_urls[key])
            return
        with lock:
            fetched[f"{source}/{board}"] = postings
            boards.append((source, board, name, "import"))

    if new_urls:
        report(f"Checking {len(new_urls)} careers pages…")
        with ContextThreadPool(max_workers=FETCH_CONCURRENCY) as pool:
            list(pool.map(fetch, new_urls))

    save_companies(service, boards, fetched)
    removed = remove_duplicate_names(service) if boards else set()
    existing |= {(source, board) for source, board, _, _ in boards if (source, board) in removed}
    boards = [entry for entry in boards if (entry[0], entry[1]) not in removed]
    added = {(source, board) for source, board, _, _ in boards}
    record_kinds(service, {key: entry.kind for key, entry in named.items() if key in added})
    empty = sorted(name for source, board, name, _ in boards if not fetched.get(f"{source}/{board}"))
    return ImportResult(sorted(name for _, _, name, _ in boards), len(existing), not_found, empty)


def hiring_thread_postings(
    client: Any,
    settings: Settings,
    service: Rest,
    usage: Usage,
    report: Callable[[str], None],
    read_posts: Callable[[], list[HiringPost]],
    extractor: Callable[..., list[Posting]],
) -> list[Posting]:
    """
    Roles from recent Hacker News 'Who is hiring?' posts. Each post is read by
    Claude once; its roles are saved as postings and reused by later searches.
    Posts that listed no role are read again next time.
    """
    try:
        posts = read_posts()
    except Exception as error:
        logger.warning("reading Hacker News failed: %s", error)
        return []
    if not posts:
        return []
    since = min(post.posted_at for post in posts).isoformat()
    rows = service.select("postings", {"select": "*", "source": "eq.hackernews", "posted_at": f"gte.{since}"})
    saved = [Posting.model_validate(row) for row in rows]
    read = {posting.external_id.split("-")[0] for posting in saved}
    new = [post for post in posts if post.id not in read]
    if not new:
        return saved
    report("Gathering open jobs…")
    found = extractor(client, settings.discovery_model, new, usage)
    if found:
        service.insert("postings", [p.model_dump(mode="json") for p in found], on_conflict="source,external_id")
    return saved + found


def remove_duplicate_names(service: Rest) -> set[tuple[str, str]]:
    """
    Keeps one directory entry per company name, ignoring case: the board with
    the most open jobs, or the older entry on a tie. Returns the removed boards.
    """
    rows = service.select("companies", {"select": "id,source,board,name,open_jobs,created_at"})
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(" ".join(row["name"].lower().split()), []).append(row)

    removed: set[tuple[str, str]] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        _, *rest = sorted(group, key=lambda row: (-row["open_jobs"], row["created_at"]))
        service.delete("companies", {"id": f"in.({','.join(row['id'] for row in rest)})"})
        removed |= {(row["source"], row["board"]) for row in rest}
    return removed


# Short forms written out before titles are compared across sources.
TITLE_ABBREVIATIONS = {"sr": "senior", "jr": "junior", "eng": "engineer", "engr": "engineer"}


def one_per_job(postings: list[Posting]) -> list[Posting]:
    """
    One posting per job across sources: the same company name and title
    ('Sr Software Engineer, Full-Stack' and 'Senior Software Engineer, Full Stack')
    count as one job. A company board's posting is kept over a Hacker News one.
    """
    chosen: dict[tuple[str, str], Posting] = {}
    for p in postings:
        words = re.findall(r"[a-z0-9]+", p.title.lower())
        key = (compact(p.company), " ".join(TITLE_ABBREVIATIONS.get(word, word) for word in words))
        if key not in chosen or (chosen[key].source == "hackernews" and p.source != "hackernews"):
            chosen[key] = p
    return list(chosen.values())


def labeled_examples(user: Rest) -> list[LabeledJob]:
    """
    The user's most recently updated jobs marked good and bad, up to
    MAX_EXAMPLES of each, or none until both labels have MIN_EXAMPLES.
    """
    by_label: dict[str, list[LabeledJob]] = {}
    for label in ("good", "bad"):
        rows = user.select(
            "applications",
            {
                "select": "posting:postings(title,company,location,workplace_type,years_experience,tech_stack)",
                "fit_label": f"eq.{label}",
                "order": "updated_at.desc",
                "limit": str(MAX_EXAMPLES),
            },
        )
        by_label[label] = [labeled_job(label, row["posting"]) for row in rows]
    if any(len(jobs) < MIN_EXAMPLES for jobs in by_label.values()):
        return []
    return [*by_label["good"], *by_label["bad"]]


def labeled_job(label: str, posting: dict[str, Any]) -> LabeledJob:
    """A labeled example from a postings row."""
    return LabeledJob(
        label=label,
        title=posting["title"],
        company=posting["company"],
        location=posting["location"],
        workplace_type=posting["workplace_type"],
        years_experience=posting["years_experience"],
        tech_stack=tuple(posting["tech_stack"] or ()),
    )
