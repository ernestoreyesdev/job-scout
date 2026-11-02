import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

SourceName = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "workable",
    "recruitee",
    "workday",
    "personio",
    "bamboohr",
    "icims",
    "jobvite",
    "hackernews",
]
WorkplaceType = Literal["onsite", "hybrid", "remote"]

BOARD_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Posting(BaseModel):
    """A job posting normalized across sources; mirrors the postings table."""

    source: SourceName
    board: str
    external_id: str
    title: str
    company: str
    location: str | None
    url: str
    description: str
    posted_at: datetime | None
    workplace_type: WorkplaceType | None = None


@dataclass
class CompanyBoard:
    """The board a company was found on and its open postings, which can be none."""

    source: SourceName
    board: str
    name: str
    postings: list[Posting]


class BoardNotFound(Exception):
    pass


class CompanyNotFound(Exception):
    pass


class JobSource(ABC):
    """
    One applicant tracking system's public job board API. This class owns what
    every system shares: the HTTP client, turning "not found" into BoardNotFound,
    guessing board names from a company name and reading boards from job page
    URLs. Each subclass only knows its endpoints and how to map its jobs to Posting.
    """

    name: ClassVar[SourceName]
    label: ClassVar[str]
    # Hosts of the system's public job pages, where the first path segment is the board.
    board_hosts: ClassVar[tuple[str, ...]]
    # Path segments on those hosts that are site pages rather than boards.
    reserved_paths: ClassVar[frozenset[str]] = frozenset()
    # Response codes meaning the board doesn't exist.
    not_found_statuses: ClassVar[frozenset[int]] = frozenset({404})
    # Most jobs one fetch can return; a board at this size may have more that weren't listed.
    max_jobs: ClassVar[int | None] = None

    def __init__(self, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30, headers={"User-Agent": "job-finder"})

    @abstractmethod
    def fetch(self, board: str, company: str) -> list[Posting]:
        """Open postings on `board`; `company` names them when the source doesn't. Raises BoardNotFound."""

    def describe(self, posting: Posting) -> str:
        """Full description of a posting; systems whose job lists omit it fetch it here."""
        return posting.description

    def board_candidates(self, company: str) -> list[str]:
        """Spellings companies commonly use as board names: 'Scale AI' -> scaleai, scale-ai."""
        words = re.findall(r"[a-z0-9]+", company.lower())
        candidates = ["".join(words), "-".join(words)]
        return [c for i, c in enumerate(candidates) if c and c not in candidates[:i]]

    def default_name(self, board: str) -> str:
        """Company name to show for a board before its jobs say otherwise: 'scale-ai' -> 'Scale Ai'."""
        return board.replace("-", " ").title()

    def board_from_url(self, url: str) -> str | None:
        """The board a public job page URL belongs to, or None when the URL isn't one of this system's boards."""
        parsed = urlparse(url)
        if (parsed.hostname or "") not in self.board_hosts:
            return None
        board = parsed.path.strip("/").split("/")[0].lower()
        return board if BOARD_SLUG.match(board) and board not in self.reserved_paths else None

    def _get_json(self, board: str, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a board's JSON; a not-found status means the board doesn't exist on this system."""
        return self._json(board, self._http.get(url, params=params))

    def _post_json(self, board: str, url: str, body: dict[str, Any]) -> Any:
        """POST to a board's JSON endpoint; a not-found status means the board doesn't exist on this system."""
        return self._json(board, self._http.post(url, json=body))

    def _get_text(self, board: str, url: str, params: dict[str, Any] | None = None) -> str:
        """GET a board's page or feed as text; a not-found status means the board doesn't exist on this system."""
        return self._checked(board, self._http.get(url, params=params)).text

    def _json(self, board: str, res: httpx.Response) -> Any:
        return self._checked(board, res).json()

    def _checked(self, board: str, res: httpx.Response) -> httpx.Response:
        if res.status_code in self.not_found_statuses:
            raise BoardNotFound(f"{self.label} board '{board}' does not exist.")
        res.raise_for_status()
        return res

    def careers_url(self, board: str) -> str:
        """The company's public job listing page on this system."""
        return f"https://{self.board_hosts[0]}/{board}"
