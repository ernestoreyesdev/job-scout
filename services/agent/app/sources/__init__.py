import re

from app.sources.ashby import AshbySource
from app.sources.base import BoardNotFound, CompanyNotFound, JobSource, Posting, SourceName
from app.sources.greenhouse import GreenhouseSource
from app.sources.lever import LeverSource


def all_sources() -> list[JobSource]:
    return [GreenhouseSource(), LeverSource(), AshbySource()]


def board_candidates(company: str) -> list[str]:
    """Spellings companies commonly use as board IDs: 'Scale AI' -> scaleai, scale-ai."""
    words = re.findall(r"[a-z0-9]+", company.lower())
    candidates = ["".join(words), "-".join(words)]
    return [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]


def find_company(company: str, sources: list[JobSource] | None = None) -> list[Posting]:
    """
    Open postings for a company, trying each spelling on each source. The board
    with the most open postings wins, since companies that switch systems often
    leave an old board behind with a few stale jobs.
    """
    best: list[Posting] | None = None
    for board in board_candidates(company):
        for source in sources if sources is not None else all_sources():
            try:
                postings = source.fetch(board, display_name(company))
            except BoardNotFound:
                continue
            if best is None or len(postings) > len(best):
                best = postings

    if best is None:
        raise CompanyNotFound(f"Couldn't find job listings for {company}.")
    return best


def display_name(company: str) -> str:
    """Capitalizes each word of an all-lowercase name ('ramp' -> 'Ramp'); keeps casing the user typed."""
    name = " ".join(company.split())
    return name.title() if name == name.lower() else name


def fetch_board(source: SourceName, board: str, company: str, sources: list[JobSource] | None = None) -> list[Posting]:
    """Open postings on one known board; raises BoardNotFound when it no longer exists."""
    by_name = {s.name: s for s in (sources if sources is not None else all_sources())}
    return by_name[source].fetch(board, company)
