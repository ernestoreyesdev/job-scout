import logging
import re
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from app.agents.discovery.agent import FoundBoard, discover_boards, find_company_boards, name_companies
from app.agents.hiring_threads.agent import HiringPost, cached_recent_posts, extract_jobs, post_id
from app.agents.lessons.agent import refresh_lessons, saved_lessons
from app.agents.schemas import CompanyName, RescoreScope, SearchRule
from app.agents.scoring.agent import score_and_save
from app.agents.scoring.prompts import LabeledJob, Lesson
from app.agents.titles.agent import related_titles
from app.config import Settings
from app.db import Rest
from app.embeddings import embed_jobs, job_text, resume_chunks
from app.sources import (
    board_from_url,
    careers_url,
    default_name,
    describe,
    display_name,
    fetch_board,
    fetch_live,
    find_company,
    is_complete,
)
from app.sources.base import BoardNotFound, CompanyBoard, CompanyNotFound, Posting, SourceName
from app.sources.filters import matches_rule
from app.telemetry import ContextThreadPool, timed

logger = logging.getLogger("agent")

# Web discovery runs while the directory has fewer companies than this, for keyword sets it hasn't run for, and otherwise once per interval.
MIN_DIRECTORY = 25
DISCOVERY_INTERVAL = timedelta(days=7)
# Daily discovery picks from keyword sets searched within this many days, and runs this many of them.
DISCOVERY_SEARCH_DAYS = 30
DAILY_DISCOVERIES = 2
# Boards from a company's web lookup checked before giving up.
MAX_LOOKUP_BOARDS = 5
# A link in a Hacker News post's text.
LINK = re.compile(r"https?://[^\s)\]\"'<>]+")
# Company kinds never searched, refreshed or saved.
SKIPPED_KINDS = frozenset({"staffing"})
# Jobs scored per company in a search across the directory.
MAX_PER_COMPANY = 3
# A search scores this many times its job limit and keeps the best-scoring ones.
POOL_FACTOR = 2
# With a min score, a search scores another pool while fewer jobs than its limit pass, up to this many pools.
MAX_SCORING_ROUNDS = 3
FETCH_CONCURRENCY = 16
FETCH_RETRY_SECONDS = 2.0
# Consecutive searches that find a board gone before it leaves the directory.
MAX_MISSED_CHECKS = 3
# Most recent jobs per label shown to scoring, and how many of each label it takes before any are shown.
MAX_EXAMPLES = 15
MIN_EXAMPLES = 3
# A board fetched this recently is read from postings; the daily refresh keeps boards inside it.
FRESH_BOARD_HOURS = 25
# Jobs saved per request, requests sent at once, and days a closed job nobody tracks is kept.
STORE_CHUNK = 100
STORE_CONCURRENCY = 1
STALE_JOB_DAYS = 30
# Jobs without an embedding that a refresh loads and embeds at a time, newest first, and how many are saved per request.
EMBED_BATCH = 1000
EMBED_CHUNK = 200
# Jobs ranked against the resume per database call, and how many calls run at once.
RANK_BATCH = 5000
RANK_CONCURRENCY = 4
# The refresh workflow's timeout; a refresh still unfinished after it was cut off.
REFRESH_TIME_LIMIT = timedelta(hours=5)
# The jobs each page lists, as a filter on applications.
RESCORE_SCOPES: dict[RescoreScope, str] = {"tracker": "in_tracker.eq.true", "jobs": "status.neq.new"}

BoardKey = tuple[str, str]


class Board(NamedTuple):
    source: str
    board: str
    name: str
    found_by: str

    @property
    def key(self) -> BoardKey:
        return self.source, self.board


@dataclass
class SearchResult:
    found: int
    matched: int
    scored: int = 0
    failed: int = 0
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
    report: Callable[[str], None],
    finder: Callable[[str], CompanyBoard] = find_company,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_board,
    discover: Callable[..., list[FoundBoard]] = discover_boards,
    describer: Callable[[Posting], str] = describe,
    lookup: Callable[..., list[FoundBoard]] = find_company_boards,
    namer: Callable[..., dict[tuple[str, str], CompanyName]] = name_companies,
    read_posts: Callable[[], list[HiringPost]] = cached_recent_posts,
    extractor: Callable[..., list[Posting]] = extract_jobs,
    expander: Callable[..., list[str]] = related_titles,
    embed: Callable[[list[str]], list[list[float]]] = embed_jobs,
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
                found = web_lookup(rule.company, client, settings, fetcher, lookup)
            entry = Board(found.source, found.board, found.name, "lookup")
            record_board_checks(service, [entry], {entry.key: found.postings}, [])
            label_if_new(found, client, settings, service, namer)
            remove_duplicate_names(service)
        if not found.postings:
            report(f"Found {found.name}, but it has no open jobs listed.")
            return SearchResult(0, 0, company=found.name)
        everything = found.postings
    else:
        with ContextThreadPool(max_workers=2) as pool:
            hacker_news = pool.submit(
                timed_call, timings, "hacker_news", hiring_thread_postings, client, settings, service, report, read_posts, extractor
            )
            everything, unreachable, fetches = timed_call(
                timings, "companies", directory_postings, rule, client, settings, user, service, report, fetcher, discover, namer
            )
            everything = everything + hacker_news.result()

    with timed(timings, "titles"):
        titles = expander(client, settings.discovery_model, rule.keywords) if everything else []
    if titles:
        logger.info("related titles", extra={"keywords": rule.keywords, "titles": titles})
    report("Matching jobs to your search…")
    keywords = [*rule.keywords, *titles]
    matched = [p for p in everything if matches_rule(p, rule, keywords)]
    if not matched:
        report("No jobs match your search.")
        return SearchResult(len(everything), 0, unreachable_boards=unreachable, board_fetches=fetches)

    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    matched = one_per_job(one_per_title(matched))
    tracked_rows = user.select("applications", {"select": "posting_id,fit_label,posting:postings(company,title)"})
    tracked = {row["posting_id"] for row in tracked_rows}
    tracked_jobs = {job_key(row["posting"]["company"], row["posting"]["title"]) for row in tracked_rows}
    labels = Counter(row["fit_label"] for row in tracked_rows if row["fit_label"])
    fresh = [(saved_id(p), p) for p in matched if saved_id(p) not in tracked and job_key(p.company, p.title) not in tracked_jobs]
    per_company = None if rule.company else MAX_PER_COMPANY
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
            len(everything), len(matched), kept=len(newest), unreachable_boards=unreachable, board_fetches=fetches
        )

    if resume_id is None or resume_text is None:
        raise ValueError("Scoring needs a resume.")
    pool_size = rule.limit * POOL_FACTOR
    rounds = MAX_SCORING_ROUNDS if rule.min_score is not None else 1
    if len(fresh) > pool_size * rounds:
        report("Matching jobs to your search…")
        with timed(timings, "shortlist"):
            fresh = by_resume_fit(fresh, resume_text, service, embed)
    todo: list[tuple[str, Posting]] = []
    scores: dict[str, int] = {}
    scored = failed = picked = 0
    examples: list[LabeledJob] = []
    lessons: list[Lesson] = []
    for round_number in range(rounds):
        chosen = pick(fresh, pool_size * (round_number + 1), per_company)
        if len(chosen) == picked:
            break
        batch = with_descriptions(chosen[picked:], service, describer)
        picked = len(chosen)
        report("Scoring jobs against your resume…" if round_number == 0 else "Scoring more jobs to reach your minimum score…")
        if round_number == 0:
            with timed(timings, "examples"):
                examples = labeled_examples(user, service, batch, embed, labels)
            with timed(timings, "lessons"):
                lessons = current_lessons(client, settings, user, user_id)
        with timed(timings, "scoring"):
            scoring = score_and_save(
                client=client,
                model=settings.scoring_model,
                effort=settings.scoring_effort,
                todo=batch,
                resume_id=resume_id,
                resume_text=resume_text,
                user_id=user_id,
                user=user,
                service=service,
                report=report,
                examples=examples,
                lessons=lessons,
                min_score=rule.min_score,
            )
        todo += batch
        scores.update(scoring.scores)
        scored += scoring.scored
        failed += scoring.failed
        if rule.min_score is None or sum(score >= rule.min_score for score in scores.values()) >= rule.limit:
            break
    kept = keep_best(user, todo, scores, rule.limit, rule.min_score)
    return SearchResult(
        len(everything),
        len(matched),
        scored,
        failed,
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
    report: Callable[[str], None],
    fetcher: Callable[[str, str, str], list[Posting]],
    discover: Callable[..., list[FoundBoard]],
    namer: Callable[..., dict[tuple[str, str], CompanyName]],
) -> tuple[list[Posting], list[str], list[dict[str, Any]]]:
    """
    Open jobs at every directory company the user hasn't hidden, topping the
    directory up from the web while it's small or once a week. Staffing
    agencies are left out, and none of their jobs are saved. Returns the jobs,
    the unreachable boards and each board fetch's timing.
    """
    directory = service.select("companies", {"select": "id,source,board,name,found_by,missed_checks,kind,open_jobs,checked_at"})
    choices = {row["company_id"]: row["hidden"] for row in user.select("hidden_companies", {"select": "company_id,hidden"})}
    known = {(c["source"], c["board"]) for c in directory}
    boards = [
        Board(c["source"], c["board"], c["name"], c["found_by"])
        for c in directory
        if c["kind"] not in SKIPPED_KINDS and not choices.get(c["id"], False)
    ]
    skipped: set[BoardKey] = set()
    kinds: dict[BoardKey, str] = {}

    if len(directory) < MIN_DIRECTORY or discovery_due(service, rule.keywords):
        report("Gathering open jobs…")
        found = discover(client, settings.discovery_model, rule.keywords, rule.workplace_types, rule.location)
        new = [b for b in found if (b.source, b.board) not in known]
        named = namer(client, settings.discovery_model, new) if new else {}
        kinds = {key: entry.kind for key, entry in named.items()}
        boards += [
            Board(
                b.source,
                b.board,
                named[(b.source, b.board)].name if (b.source, b.board) in named else default_name(b.source, b.board),
                "discovery",
            )
            for b in new
        ]
        skipped = {key for key, kind in kinds.items() if kind in SKIPPED_KINDS}
        service.insert(
            "directory_discoveries",
            {"keywords": rule.keywords, "boards_found": len(found), "boards_added": len(new)},
        )

    sizes = {(c["source"], c["board"]): c.get("open_jobs") or 0 for c in directory}
    boards.sort(key=lambda entry: sizes.get(entry.key, 0), reverse=True)
    since = datetime.now(UTC) - timedelta(hours=FRESH_BOARD_HOURS)
    fresh = {
        (c["source"], c["board"])
        for c in directory
        if c.get("checked_at") and datetime.fromisoformat(c["checked_at"]) >= since
    }
    report("Gathering open jobs…")
    stored = stored_jobs(service, [entry for entry in boards if entry.key in fresh])
    fetched, gone, unreachable, fetches = fetch_boards([entry for entry in boards if entry.key not in fresh], fetcher, report)
    fetches += [
        {"board": board_label(key), "source": key[0], "ms": 0, "jobs": len(jobs), "outcome": "cached"}
        for key, jobs in stored.items()
    ]

    record_board_checks(service, boards, fetched, [c for c in directory if (c["source"], c["board"]) in gone], skipped)
    if any(entry.found_by == "discovery" and entry.key not in known and entry.key in fetched for entry in boards):
        remove_duplicate_names(service)
    if kinds:
        record_kinds(service, {key: kind for key, kind in kinds.items() if key in fetched})
    listed = {**stored, **fetched}
    postings = [p for key, found in listed.items() if key not in skipped for p in found]
    return postings, sorted(unreachable), fetches


def save_companies(service: Rest, boards: list[Board], postings: dict[BoardKey, list[Posting]]) -> None:
    """Records each confirmed board in the directory with its open job count."""
    if not boards:
        return
    now = datetime.now(UTC).isoformat()
    rows = []
    for source, board, name, found_by in boards:
        jobs = postings.get((source, board), [])
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
    Fills in descriptions from postings, then fetches the ones a system's job
    list left out and saves the ones that come back with text. Jobs whose
    description can't be fetched are dropped.
    """
    missing = [posting_id for posting_id, posting in todo if not posting.description]
    saved = (
        {row["id"]: row["description"] for row in service.select("postings", {"select": "id,description", "id": f"in.({','.join(missing)})"})}
        if missing
        else {}
    )
    ready: list[tuple[str, Posting]] = []
    described: list[Posting] = []
    for posting_id, posting in todo:
        if not posting.description and saved.get(posting_id):
            posting = posting.model_copy(update={"description": saved[posting_id]})
        if posting.description:
            ready.append((posting_id, posting))
            continue
        try:
            full = posting.model_copy(update={"description": describer(posting)})
        except Exception as error:
            logger.warning("describing %s/%s failed: %s", posting.source, posting.external_id, error)
            continue
        ready.append((posting_id, full))
        if full.description:
            described.append(full)
    if described:
        service.insert("postings", [p.row() for p in described], on_conflict="source,external_id")
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
    fetcher: Callable[[str, str, str], list[Posting]],
    lookup: Callable[..., list[FoundBoard]],
) -> CompanyBoard:
    """
    Finds a company's board through a web search when no spelling of its name
    matched. A board counts only when its name or its jobs' company name
    contains the company's name; the one with the most postings wins.
    """
    wanted = compact(company)
    found = lookup(client, settings.discovery_model, company)
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
    (ties go to the newer job) and takes the rest off it, keeping their scores
    so later searches skip them. Returns how many were kept.
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
        record_kind(service, source, board, kind)


def label_if_new(
    found: CompanyBoard,
    client: Any,
    settings: Settings,
    service: Rest,
    namer: Callable[..., dict[tuple[str, str], CompanyName]],
) -> None:
    """Labels a company found by name the first time it's found; its name stays the one its board gave."""
    rows = service.select(
        "companies", {"select": "kind", "source": f"eq.{found.source}", "board": f"eq.{found.board}"}
    )
    if rows and rows[0].get("kind"):
        return
    named = namer(client, settings.discovery_model, [FoundBoard(found.source, found.board, [found.name])])
    if (found.source, found.board) in named:
        record_kind(service, found.source, found.board, named[(found.source, found.board)].kind)


def rescore(
    *,
    client: Any,
    settings: Settings,
    resume_id: str,
    resume_text: str,
    user_id: str,
    user: Rest,
    service: Rest,
    report: Callable[[str], None],
    scope: RescoreScope,
    describer: Callable[[Posting], str] = describe,
    embed: Callable[[list[str]], list[list[float]]] = embed_jobs,
    timings: dict[str, int] | None = None,
) -> list[Posting]:
    """
    Scores the jobs on the user's Tracker or on Jobs, as `scope` says, that
    were scored against another resume or not scored at all. Their status,
    notes and place on the Tracker stay as they are. Returns the jobs it scored.
    """
    rows = user.select(
        "applications",
        {
            "select": f"posting_id,{EDITED_FIELDS},posting:postings({','.join(Posting.model_fields)})",
            "and": f"(or(resume_id.is.null,resume_id.neq.{resume_id}),{RESCORE_SCOPES[scope]})",
        },
    )
    todo = [(row["posting_id"], with_edits(row)) for row in rows]
    if not todo:
        report("Every job is already scored with your current resume.")
        return []
    report("Scoring jobs against your resume…")
    todo = with_descriptions(todo, service, describer)
    with timed(timings, "examples"):
        examples = labeled_examples(user, service, todo, embed, label_counts(user))
    lessons = saved_lessons(user, datetime.now(UTC))
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
            report=report,
            examples=examples,
            lessons=lessons,
        )
    return [posting for posting_id, posting in todo if posting_id in scoring.scores]


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
    report: Callable[[str], None],
    finder: Callable[[str], CompanyBoard] = find_company,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_board,
    namer: Callable[..., dict[tuple[str, str], CompanyName]] = name_companies,
    origin: str = "import",
) -> ImportResult:
    """
    Adds companies to the directory from careers page URLs or company names, recorded as found by `origin`.
    Names are tried on every system's spellings; URLs are read on the system
    they belong to, after one call names and labels every new company, so
    their jobs carry the company's real name.
    """
    known = {(c["source"], c["board"]) for c in service.select("companies", {"select": "source,board"})}
    lock = threading.Lock()
    by_name: dict[tuple[str, str], tuple[str, CompanyBoard]] = {}
    by_url: dict[tuple[SourceName, str], str] = {}
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
    named = namer(client, settings.discovery_model, candidates) if candidates else {}

    fetched = {(r.source, r.board): r.postings for _, r in new_names.values()}
    boards = [Board(r.source, r.board, r.name, origin) for _, r in new_names.values()]

    def fetch(key: tuple[SourceName, str]) -> None:
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
            fetched[key] = postings
            boards.append(Board(source, board, name, origin))

    if new_urls:
        report(f"Checking {len(new_urls)} careers pages…")
        with ContextThreadPool(max_workers=FETCH_CONCURRENCY) as pool:
            list(pool.map(fetch, new_urls))

    save_companies(service, boards, fetched)
    removed = remove_duplicate_names(service) if boards else set()
    existing |= {entry.key for entry in boards if entry.key in removed}
    boards = [entry for entry in boards if entry.key not in removed]
    added = {entry.key for entry in boards}
    record_kinds(service, {key: entry.kind for key, entry in named.items() if key in added})
    empty = sorted(entry.name for entry in boards if not fetched.get(entry.key))
    return ImportResult(sorted(entry.name for entry in boards), len(existing), not_found, empty)


def hiring_thread_postings(
    client: Any,
    settings: Settings,
    service: Rest,
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
    rows = service.select("postings", {"select": ",".join(Posting.model_fields), "source": "eq.hackernews", "posted_at": f"gte.{since}"})
    saved = [Posting.model_validate(row) for row in rows]
    read = {post_id(posting) for posting in saved}
    new = [post for post in posts if post.id not in read]
    if not new:
        return saved
    report("Gathering open jobs…")
    found = extractor(client, settings.discovery_model, new)
    if found:
        rows = service.insert("postings", [p.row() for p in found], on_conflict="source,external_id", select="id,source,external_id")
        set_ids(found, rows)
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
        key = job_key(p.company, p.title)
        if key not in chosen or (chosen[key].source == "hackernews" and p.source != "hackernews"):
            chosen[key] = p
    return list(chosen.values())


def labeled_examples(
    user: Rest,
    service: Rest,
    todo: list[tuple[str, Posting]],
    embed: Callable[[list[str]], list[list[float]]],
    labels: Counter[str],
) -> list[LabeledJob]:
    """
    The user's jobs marked good and bad nearest the jobs being scored, up to
    MAX_EXAMPLES of each, or none until both labels have MIN_EXAMPLES. Jobs
    among either without an embedding are embedded first. When embedding or
    the nearest lookup fails, the most recently updated ones are used. `labels`
    counts the user's jobs per label.
    """
    if not todo or labels["good"] < MIN_EXAMPLES or labels["bad"] < MIN_EXAMPLES:
        return []
    try:
        return nearest_examples(user, service, todo, embed)
    except Exception as error:
        logger.warning("picking labeled examples by similarity failed: %s", error)
        return recent_examples(user)


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


def save_embeddings(service: Rest, jobs: list[tuple[str, str]], embed: Callable[[list[str]], list[list[float]]]) -> None:
    """Embeds each (posting id, text) and saves the vectors in one call."""
    if not jobs:
        return
    vectors = embed([text for _, text in jobs])
    service.rpc(
        "set_posting_embeddings",
        {"embeddings": [{"id": posting_id, "embedding": vector} for (posting_id, _), vector in zip(jobs, vectors)]},
    )


def recent_examples(user: Rest) -> list[LabeledJob]:
    """The user's most recently updated jobs marked good and bad, up to MAX_EXAMPLES of each."""
    examples: list[LabeledJob] = []
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
        examples += [labeled_job(label, row["posting"]) for row in rows]
    return examples


def nearest_examples(
    user: Rest, service: Rest, todo: list[tuple[str, Posting]], embed: Callable[[list[str]], list[list[float]]]
) -> list[LabeledJob]:
    """Embeds the jobs being scored and the labeled jobs that lack an embedding, then returns those nearest the batch."""
    ids = [posting_id for posting_id, _ in todo]
    labeled = user.select(
        "applications",
        {"select": "posting_id,posting:postings!inner(title,company,location,description)", "fit_label": "not.is.null"},
    )
    candidates = ids + [row["posting_id"] for row in labeled]
    embedded = {
        row["posting_id"]
        for row in service.select("posting_embeddings", {"select": "posting_id", "posting_id": f"in.({','.join(candidates)})"})
    }
    pending = {posting_id: job_text(p.title, p.company, p.location, p.description) for posting_id, p in todo if posting_id not in embedded}
    for row in labeled:
        if row["posting_id"] not in embedded:
            pending.setdefault(row["posting_id"], job_text(**row["posting"]))
    save_embeddings(service, list(pending.items()), embed)
    rows = user.rpc("nearest_labeled_jobs", {"job_ids": ids, "per_label": MAX_EXAMPLES})
    return [labeled_job(row["fit_label"], row["posting"]) for row in rows]


def fetch_boards(
    boards: list[Board], fetcher: Callable[[str, str, str], list[Posting]], report: Callable[[str], None]
) -> tuple[dict[BoardKey, list[Posting]], list[BoardKey], list[str], list[dict[str, Any]]]:
    """
    Fetches boards FETCH_CONCURRENCY at a time, retrying a failed fetch once.
    Returns the jobs by board, the boards that are gone, the "source/board" of
    the ones that couldn't be reached, and how long each fetch took and how it ended.
    """
    lock = threading.Lock()
    fetched: dict[BoardKey, list[Posting]] = {}
    gone: list[BoardKey] = []
    unreachable: list[str] = []
    fetches: list[dict[str, Any]] = []

    def fetch(entry: Board) -> None:
        source, board, name, _ = entry
        key = board_label(entry.key)
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
                    gone.append(entry.key)
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
            fetched[entry.key] = postings
            record("ok", len(postings))
        report("Gathering open jobs…")

    with ContextThreadPool(max_workers=FETCH_CONCURRENCY) as pool:
        list(pool.map(fetch, boards))

    return fetched, gone, unreachable, fetches


def store_jobs(service: Rest, fetched: dict[BoardKey, list[Posting]], since: str | None = None) -> tuple[int, int]:
    """
    Saves every fetched job to postings as open, with its description's hash
    instead of the description, writing only new, changed and reopened ones,
    sets each job's id, and closes the jobs a complete fetch of their board no
    longer lists. Requests run STORE_CONCURRENCY at a time. Returns how many
    jobs were created at or after `since`, a database time, and how many closed.
    """
    unique = {(p.source, p.external_id): p for postings in fetched.values() for p in postings}
    rows = [p.listing_row() for p in unique.values()]
    chunks = [rows[i : i + STORE_CHUNK] for i in range(0, len(rows), STORE_CHUNK)]
    complete = [key for key, postings in fetched.items() if is_complete(key[0], postings)]

    def save(chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return service.rpc("save_postings", {"jobs": chunk})

    def close(key: BoardKey) -> int:
        source, board = key
        listed = [p.external_id for p in fetched[key]]
        return service.rpc("close_unlisted_postings", {"job_source": source, "job_board": board, "listed": listed})

    with ContextThreadPool(max_workers=STORE_CONCURRENCY) as pool:
        saved = [row for chunk in pool.map(save, chunks) for row in chunk]
        closed = sum(pool.map(close, complete))
    set_ids([p for postings in fetched.values() for p in postings], saved)
    return sum(1 for row in saved if since and row["created_at"] >= since), closed


def stored_jobs(service: Rest, boards: list[Board]) -> dict[BoardKey, list[Posting]]:
    """The open jobs saved for each board, without descriptions, which scoring loads when needed."""
    jobs: dict[BoardKey, list[Posting]] = {entry.key: [] for entry in boards}
    if not jobs:
        return jobs
    names = ",".join(f'"{board}"' for board in sorted({entry.board for entry in boards}))
    params = {
        "select": "id,source,board,external_id,title,company,location,url,posted_at,workplace_type",
        "board": f"in.({names})",
        "closed_at": "is.null",
    }
    for row in service.select_all("postings", params):
        key = (row["source"], row["board"])
        if key in jobs:
            jobs[key].append(Posting.model_validate({**row, "description": ""}))
    return jobs


def refresh_boards(
    service: Rest,
    fetcher: Callable[[str, str, str], list[Posting]] = fetch_live,
    embed: Callable[[list[str]], list[list[float]]] = embed_jobs,
    client: Any = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Marks earlier refreshes that were cut off as stopped and, with a Claude
    client, grows the directory with grow_directory. Then fetches every
    directory board from its system except staffing agencies, saves the jobs,
    closes the ones no longer listed, keeps one directory entry per company
    name, embeds every open job that has none from the description just
    fetched, deletes jobs closed STALE_JOB_DAYS ago that nobody tracks, and
    records the refresh in board_refreshes. Returns that record.
    """
    now = datetime.now(UTC)
    service.update(
        "board_refreshes",
        {"finished_at": "is.null", "stopped_at": "is.null", "started_at": f"lt.{(now - REFRESH_TIME_LIMIT).isoformat()}", "select": "id"},
        {"stopped_at": now.isoformat()},
    )
    previous = service.select(
        "board_refreshes", {"select": "started_at", "finished_at": "not.is.null", "order": "started_at.desc", "limit": "1"}
    )
    [refresh] = service.insert("board_refreshes", {}, select="id,started_at")
    if client is not None and settings is not None:
        grow_directory(service, client, settings, previous[0]["started_at"] if previous else None)
    directory = service.select("companies", {"select": "id,source,board,name,found_by,missed_checks,kind,open_jobs"})
    directory = [c for c in directory if c["kind"] not in SKIPPED_KINDS]
    directory.sort(key=lambda c: c.get("open_jobs") or 0, reverse=True)
    boards = [Board(c["source"], c["board"], c["name"], c["found_by"]) for c in directory]
    fetched, gone, unreachable, fetches = fetch_boards(boards, fetcher, lambda _: None)
    gone_companies = [c for c in directory if (c["source"], c["board"]) in gone]
    new, closed = record_board_checks(service, boards, fetched, gone_companies, since=refresh["started_at"])
    remove_duplicate_names(service)
    descriptions = {(p.source, p.external_id): p.description for postings in fetched.values() for p in postings}
    embedded = 0
    while (batch := embed_missing(service, embed, EMBED_BATCH, descriptions)) == EMBED_BATCH:
        embedded += batch
    embedded += batch
    deleted = service.rpc("delete_stale_postings", {"days": STALE_JOB_DAYS})
    summary = {
        "finished_at": datetime.now(UTC).isoformat(),
        "boards": len(fetched),
        "jobs": sum(len(postings) for postings in fetched.values()),
        "new_jobs": new,
        "closed_jobs": closed,
        "embedded_jobs": embedded,
        "deleted_jobs": deleted,
        "failures": len(unreachable),
        "board_fetches": fetches,
    }
    service.update("board_refreshes", {"id": f"eq.{refresh['id']}", "select": "id"}, summary)
    return summary


def by_resume_fit(
    fresh: list[tuple[str, Posting]], resume_text: str, service: Rest, embed: Callable[[list[str]], list[list[float]]]
) -> list[tuple[str, Posting]]:
    """
    Reorders matches by how close each job is to the nearest section of the
    resume, best first, ranking RANK_BATCH jobs per database call; jobs without
    an embedding yet follow in their order.
    """
    sections = embed(resume_chunks(resume_text))
    ids = [posting_id for posting_id, _ in fresh]
    batches = [ids[i : i + RANK_BATCH] for i in range(0, len(ids), RANK_BATCH)]
    with ContextThreadPool(max_workers=RANK_CONCURRENCY) as pool:
        ranked = pool.map(lambda batch: service.rpc("rank_postings", {"job_ids": batch, "sections": sections}), batches)
        rows = sorted((row for batch in ranked for row in batch), key=lambda row: row["similarity"], reverse=True)
    order = {row["id"]: rank for rank, row in enumerate(rows)}
    return sorted(fresh, key=lambda job: order.get(job[0], len(order)))


def embed_missing(
    service: Rest, embed: Callable[[list[str]], list[list[float]]], limit: int, descriptions: dict[tuple[str, str], str]
) -> int:
    """
    Embeds up to `limit` open jobs that have no embedding, newest first, from
    their description in `descriptions` by (source, external id), or the saved
    one when it isn't there. Returns how many.
    """
    rows = service.rpc("unembedded_postings", {"max_rows": limit})
    for i in range(0, len(rows), EMBED_CHUNK):
        save_embeddings(
            service,
            [
                (
                    row["id"],
                    job_text(
                        row["title"],
                        row["company"],
                        row["location"],
                        descriptions.get((row["source"], row["external_id"])) or row["description"],
                    ),
                )
                for row in rows[i : i + EMBED_CHUNK]
            ],
            embed,
        )
    return len(rows)


def job_key(company: str, title: str) -> tuple[str, str]:
    """
    A job as compared across sources: the company in letters and digits, and
    the title's words with short forms written out ('Sr' reads as 'Senior').
    """
    words: list[str] = re.findall(r"[a-z0-9]+", title.lower())
    return compact(company), " ".join(TITLE_ABBREVIATIONS.get(word, word) for word in words)


def record_kind(service: Rest, source: str, board: str, kind: str) -> None:
    service.update("companies", {"source": f"eq.{source}", "board": f"eq.{board}"}, {"kind": kind})


def board_label(key: BoardKey) -> str:
    """A board as "source/board", the form runs and refreshes record."""
    return f"{key[0]}/{key[1]}"


def record_board_checks(
    service: Rest,
    boards: list[Board],
    fetched: dict[BoardKey, list[Posting]],
    gone: list[dict[str, Any]],
    unsaved: set[BoardKey] | None = None,
    since: str | None = None,
) -> tuple[int, int]:
    """
    Saves the fetched jobs, except those of `unsaved` boards, records the boards
    that answered in the directory and counts a miss for each directory company
    in `gone`. Returns how many jobs were created at or after `since` and how many closed.
    """
    saved = {key: jobs for key, jobs in fetched.items() if key not in (unsaved or set())}
    new, closed = store_jobs(service, saved, since)
    save_companies(service, [entry for entry in boards if entry.key in fetched], fetched)
    record_misses(service, gone)
    return new, closed


def set_ids(postings: list[Posting], rows: list[dict[str, Any]]) -> None:
    """Sets each posting's id from saved rows with id, source and external_id."""
    ids = {(row["source"], row["external_id"]): row["id"] for row in rows}
    for posting in postings:
        posting.id = ids.get((posting.source, posting.external_id), posting.id)


def saved_id(posting: Posting) -> str:
    if posting.id is None:
        raise ValueError(f"{posting.source}/{posting.external_id} was never saved.")
    return posting.id


def label_counts(user: Rest) -> Counter[str]:
    """How many of the user's jobs carry each label."""
    return Counter(row["fit_label"] for row in user.select("applications", {"select": "fit_label", "fit_label": "not.is.null"}))


def timed_call(timings: dict[str, int] | None, step: str, fn: Callable[..., Any], *args: Any) -> Any:
    """fn(*args), its milliseconds added to timings[step]."""
    with timed(timings, step):
        return fn(*args)


def current_lessons(client: Any, settings: Settings, user: Rest, user_id: str) -> list[Lesson]:
    """
    Learns the user's lessons again when their ratings or statuses changed, then
    returns the saved ones; a failed update leaves the saved ones as they were.
    """
    now = datetime.now(UTC)
    try:
        refresh_lessons(client, settings.analysis_model, user, user_id, now)
    except Exception as error:
        logger.warning("learning preferences failed: %s", error)
    return saved_lessons(user, now)


EDITED_FIELDS = "edited_title,edited_company,edited_description"


def with_edits(row: dict[str, Any]) -> Posting:
    """The application row's posting with the user's own title, company and description in place of the job's."""
    edits = {field: row.get(f"edited_{field}") for field in ("title", "company", "description")}
    return Posting.model_validate(row["posting"]).model_copy(update={k: v for k, v in edits.items() if v})


def grow_directory(service: Rest, client: Any, settings: Settings, since: str | None) -> None:
    """
    Adds the companies of Hacker News jobs saved since `since` and runs the
    daily discovery. A step that fails is logged and skipped.
    """
    try:
        result = add_hiring_thread_companies(service, client, settings, since)
        if result:
            added, missing = len(result.added), len(result.not_found)
            logger.info("added hacker news companies", extra={"added": added, "not_found": missing})
    except Exception as error:
        logger.warning("adding hacker news companies failed: %s", error)
    try:
        logger.info("daily discovery", extra={"added": discover_for_recent_searches(service, client, settings)})
    except Exception as error:
        logger.warning("daily discovery failed: %s", error)


def add_hiring_thread_companies(
    service: Rest, client: Any, settings: Settings, since: str | None
) -> ImportResult | None:
    """
    Adds the companies of Hacker News jobs saved since `since`, or all of them
    without it: from the job board a company's post links to, else by name.
    """
    params = {"select": "id,company,description", "source": "eq.hackernews", **({"created_at": f"gte.{since}"} if since else {})}
    rows = service.select_all("postings", params)
    links: dict[str, str] = {}
    for row in rows:
        url = next((url for url in LINK.findall(row["description"] or "") if board_from_url(url)), None)
        if url:
            links.setdefault(" ".join(row["company"].lower().split()), url)
    return add_companies_by_name(service, client, settings, [row["company"] for row in rows], "hacker_news", links)


def add_companies_by_name(
    service: Rest, client: Any, settings: Settings, names: list[str], origin: str, links: dict[str, str] | None = None
) -> ImportResult | None:
    """
    Adds the companies in `names` that no directory company is named, recorded
    as found by `origin`: from the job board URL `links` gives for the lowercased
    name, else looked up on every system's spellings, where a board with no open
    jobs counts as not found. None when there were none to look up.
    """
    listed = {" ".join(c["name"].lower().split()) for c in service.select("companies", {"select": "name"})}
    wanted = {" ".join(name.split()) for name in names if name and name.strip()}
    entries = sorted((links or {}).get(name.lower(), name) for name in wanted if name.lower() not in listed)
    if not entries:
        return None
    return import_companies(
        entries=entries,
        client=client,
        settings=settings,
        service=service,
        report=lambda _: None,
        finder=find_company_with_jobs,
        origin=origin,
    )


def discover_for_recent_searches(
    service: Rest,
    client: Any,
    settings: Settings,
    discover: Callable[..., list[FoundBoard]] = discover_boards,
    namer: Callable[..., dict[tuple[str, str], CompanyName]] = name_companies,
) -> int:
    """
    Runs web discovery for up to DAILY_DISCOVERIES keyword sets searched in the
    last DISCOVERY_SEARCH_DAYS days, those discovered longest ago or never
    first, and adds the boards it finds. Returns how many it added.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=DISCOVERY_SEARCH_DAYS)).isoformat()
    runs = service.select("agent_runs", {"select": "input", "kind": "eq.search", "created_at": f"gte.{cutoff}"})
    searched: dict[frozenset[str], list[str]] = {}
    for run in runs:
        if keywords := (run.get("input") or {}).get("keywords"):
            searched.setdefault(keyword_set(keywords), keywords)
    last: dict[frozenset[str], str] = {}
    for row in service.select("directory_discoveries", {"select": "keywords,ran_at"}):
        key = keyword_set(row["keywords"])
        last[key] = max(last.get(key, ""), row["ran_at"])
    known = {(c["source"], c["board"]) for c in service.select("companies", {"select": "source,board"})}
    added = 0
    for key in sorted(searched, key=lambda key: last.get(key, ""))[:DAILY_DISCOVERIES]:
        keywords = searched[key]
        found = discover(client, settings.discovery_model, keywords, [], None)
        new = [b for b in found if (b.source, b.board) not in known]
        named = namer(client, settings.discovery_model, new) if new else {}
        names = {key: entry.name for key, entry in named.items()}
        boards = [
            Board(b.source, b.board, names.get((b.source, b.board)) or default_name(b.source, b.board), "discovery")
            for b in new
        ]
        save_companies(service, boards, {})
        record_kinds(service, {board_key: entry.kind for board_key, entry in named.items()})
        service.insert(
            "directory_discoveries", {"keywords": keywords, "boards_found": len(found), "boards_added": len(new)}
        )
        known |= {(b.source, b.board) for b in new}
        added += len(new)
    if added:
        remove_duplicate_names(service)
    return added


def find_company_with_jobs(company: str) -> CompanyBoard:
    """The board find_company finds, counting one with no open jobs as not found."""
    found = find_company(company)
    if not found.postings:
        raise CompanyNotFound(f"Couldn't find open jobs for {company}.")
    return found
