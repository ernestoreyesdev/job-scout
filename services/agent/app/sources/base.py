import hashlib
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, field_validator

from app.constants import HTTP_TIMEOUT, USER_AGENT
from app.sources.http import send

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
    "gem",
    "rippling",
    "pinpoint",
    "teamtailor",
    "polymer",
    "oracle",
    "hackernews",
    "manual",
]
WorkplaceType = Literal["onsite", "hybrid", "remote"]

BOARD_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Posting(BaseModel):
    """A job posting normalized across sources; mirrors the postings table, with its row id once saved or loaded."""

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
    id: str | None = None

    @field_validator("title", "company")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()

    def row(self) -> dict[str, Any]:
        """The columns to save, with the description's hash; an empty description is left out so a saved one stays."""
        if not self.description:
            return self.model_dump(mode="json", exclude={"id", "description"})
        return {**self.model_dump(mode="json", exclude={"id"}), "description_hash": description_hash(self.description)}

    def listing_row(self) -> dict[str, Any]:
        """The columns a refresh saves: the listing and its description's hash, without the description itself."""
        return {
            **self.model_dump(mode="json", exclude={"id", "description"}),
            "description_hash": description_hash(self.description) if self.description else None,
        }


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

    board_hosts are the hosts of the system's public job pages, where the first
    path segment is the board, and reserved_paths are the segments on them that
    are site pages. With subdomain_boards, the board is the subdomain of a board
    host instead, and reserved_paths are subdomains. not_found_statuses are the response codes meaning a board
    doesn't exist. max_jobs is the most one fetch returns, so a board at that
    size may have more. With max_requests, at most that many requests to the
    system are out at once. Every request gets the retries in app.sources.http.
    """

    name: ClassVar[SourceName]
    label: ClassVar[str]
    board_hosts: ClassVar[tuple[str, ...]]
    reserved_paths: ClassVar[frozenset[str]] = frozenset()
    subdomain_boards: ClassVar[bool] = False
    not_found_statuses: ClassVar[frozenset[int]] = frozenset({404})
    max_jobs: ClassVar[int | None] = None
    max_requests: ClassVar[int | None] = None

    def __init__(self, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
        self._requests = threading.BoundedSemaphore(self.max_requests) if self.max_requests else None

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
        if self.subdomain_boards:
            host = (parsed.hostname or "").lower()
            suffix = next((f".{h}" for h in self.board_hosts if host.endswith(f".{h}")), None)
            if suffix is None:
                return None
            board = host.removesuffix(suffix)
        elif (parsed.hostname or "") not in self.board_hosts:
            return None
        else:
            board = parsed.path.strip("/").split("/")[0].lower()
        return board if BOARD_SLUG.match(board) and board not in self.reserved_paths else None

    def _get_json(self, board: str, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a board's JSON; a not-found status means the board doesn't exist on this system."""
        return self._json(board, self._send(lambda: self._http.get(url, params=params)))

    def _post_json(self, board: str, url: str, body: dict[str, Any]) -> Any:
        """POST to a board's JSON endpoint; a not-found status means the board doesn't exist on this system."""
        return self._json(board, self._send(lambda: self._http.post(url, json=body)))

    def _get_text(self, board: str, url: str, params: dict[str, Any] | None = None) -> str:
        """GET a board's page or feed as text; a not-found status means the board doesn't exist on this system."""
        return self._checked(board, self._send(lambda: self._http.get(url, params=params))).text

    def _json(self, board: str, res: httpx.Response) -> Any:
        return self._checked(board, res).json()

    def _checked(self, board: str, res: httpx.Response) -> httpx.Response:
        if res.status_code in self.not_found_statuses:
            raise BoardNotFound(f"{self.label} board '{board}' does not exist.")
        res.raise_for_status()
        return res

    def careers_url(self, board: str) -> str:
        """The company's public job listing page on this system: its subdomain, or its path on the host."""
        if self.subdomain_boards:
            return f"https://{board}.{self.board_hosts[0]}/"
        return f"https://{self.board_hosts[0]}/{board}"

    def _send(self, request: Callable[[], httpx.Response]) -> httpx.Response:
        """Sends a request with the shared retries, each attempt within max_requests when the system sets it."""
        requests = self._requests
        if requests is None:
            return send(request)

        def limited() -> httpx.Response:
            with requests:
                return request()

        return send(limited)

    def _pages[T](self, page: Callable[[int], T], starts: range, concurrency: int) -> list[T]:
        """The pages starting at each of `starts`, `concurrency` at a time, in order, keeping the caller's logging context."""
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            return list(pool.map(lambda start: copy_context().run(page, start), starts))


def description_hash(description: str) -> str:
    """The MD5 of a description, matching Postgres's md5() of the same text."""
    return hashlib.md5(description.encode()).hexdigest()


def distinct[T](items: Iterable[T], key: Callable[[T], Hashable | None]) -> Iterator[T]:
    """Items in order, skipping ones whose key is missing or already seen."""
    seen: set[Hashable] = set()
    for item in items:
        value = key(item)
        if value is None or value in seen:
            continue
        seen.add(value)
        yield item
