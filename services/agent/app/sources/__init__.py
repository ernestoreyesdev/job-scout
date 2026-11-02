"""
Job sources: one JobSource subclass per applicant tracking system, registered
in SOURCES. Adding a system means a new module, an entry here and a new
job_source enum value in the database. See .context/job-sources.md.
"""

import threading
import time
from functools import cache

from app.sources.ashby import AshbySource
from app.sources.bamboohr import BambooHRSource
from app.sources.base import BoardNotFound, CompanyBoard, CompanyNotFound, JobSource, Posting, SourceName
from app.sources.greenhouse import GreenhouseSource
from app.sources.icims import ICIMSSource
from app.sources.jobvite import JobviteSource
from app.sources.lever import LeverSource
from app.sources.personio import PersonioSource
from app.sources.recruitee import RecruiteeSource
from app.sources.smartrecruiters import SmartRecruitersSource
from app.sources.workable import WorkableSource
from app.sources.workday import WorkdaySource

# Boards fetched within this long are served from memory.
CACHE_SECONDS = 6 * 60 * 60

_board_cache: dict[tuple[str, str], tuple[float, list[Posting]]] = {}
_board_cache_lock = threading.Lock()

SOURCES: tuple[type[JobSource], ...] = (
    GreenhouseSource,
    LeverSource,
    AshbySource,
    SmartRecruitersSource,
    WorkableSource,
    RecruiteeSource,
    WorkdaySource,
    PersonioSource,
    BambooHRSource,
    ICIMSSource,
    JobviteSource,
)


@cache
def all_sources() -> tuple[JobSource, ...]:
    """One shared instance per system; their HTTP clients are safe to use across threads."""
    return tuple(source() for source in SOURCES)


def find_company(company: str, sources: tuple[JobSource, ...] | None = None) -> CompanyBoard:
    """
    A company's board and open postings, trying each system's spellings of the
    name. The board with the most open postings wins, since companies that
    switch systems often leave an old board behind with a few stale jobs. A
    board with no postings still counts as finding the company.
    """
    name = display_name(company)
    best: CompanyBoard | None = None
    for source in sources if sources is not None else all_sources():
        for board in source.board_candidates(company):
            try:
                postings = source.fetch(board, name) if sources is not None else cached_fetch(source, board, name)
            except BoardNotFound:
                continue
            if best is None or len(postings) > len(best.postings):
                best = CompanyBoard(source.name, board, postings[0].company if postings else name, postings)

    if best is None:
        raise CompanyNotFound(f"Couldn't find job listings for {company}.")
    return best


def display_name(company: str) -> str:
    """Capitalizes each word of an all-lowercase name ('ramp' -> 'Ramp'); keeps casing the user typed."""
    name = " ".join(company.split())
    return name.title() if name == name.lower() else name


def fetch_board(source: SourceName, board: str, company: str, sources: tuple[JobSource, ...] | None = None) -> list[Posting]:
    """Open postings on one known board; raises BoardNotFound when it no longer exists."""
    if sources is not None:
        return source_named(source, sources).fetch(board, company)
    return cached_fetch(source_named(source), board, company)


def source_named(name: str, sources: tuple[JobSource, ...] | None = None) -> JobSource:
    return next(source for source in (sources if sources is not None else all_sources()) if source.name == name)


def board_from_url(url: str, sources: tuple[JobSource, ...] | None = None) -> tuple[SourceName, str] | None:
    """The (system, board) a public job page URL belongs to, or None for any other URL."""
    for source in sources if sources is not None else all_sources():
        board = source.board_from_url(url)
        if board:
            return source.name, board
    return None


def board_hosts(sources: tuple[JobSource, ...] | None = None) -> list[str]:
    """Every system's job page hosts, for limiting web searches to job boards."""
    return [host for source in (sources if sources is not None else all_sources()) for host in source.board_hosts]


def describe(posting: Posting, sources: tuple[JobSource, ...] | None = None) -> str:
    """The posting's full description, fetched from its system when the job list left it out."""
    return posting.description or source_named(posting.source, sources).describe(posting)


def default_name(source: str, board: str, sources: tuple[JobSource, ...] | None = None) -> str:
    """Company name to show for a newly found board until its jobs give the real one."""
    return source_named(source, sources).default_name(board)


def careers_url(source: str, board: str, sources: tuple[JobSource, ...] | None = None) -> str:
    """The company's public job listing page for a board."""
    return source_named(source, sources).careers_url(board)


def cached_fetch(source: JobSource, board: str, company: str) -> list[Posting]:
    """A board's postings, reused from memory for CACHE_SECONDS after a fetch; boards that don't exist aren't kept."""
    key = (source.name, board)
    with _board_cache_lock:
        hit = _board_cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    postings = source.fetch(board, company)
    with _board_cache_lock:
        _board_cache[key] = (time.monotonic(), postings)
    return postings


def is_complete(source: str, postings: list[Posting], sources: tuple[JobSource, ...] | None = None) -> bool:
    """False when a fetch hit the system's limit, so jobs missing from it may still be open."""
    limit = source_named(source, sources).max_jobs
    return limit is None or len(postings) < limit
