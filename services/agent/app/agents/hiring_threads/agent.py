import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.agents.claude import parse
from app.agents.hiring_threads.prompts import EXTRACTION_SYSTEM, extraction_message
from app.agents.schemas import HiringJobs
from app.constants import HTTP_TIMEOUT, USER_AGENT
from app.sources.base import Posting
from app.sources.text import html_to_text
from app.telemetry import ContextThreadPool

logger = logging.getLogger("agent")

API = "https://hn.algolia.com/api/v1"
POST_URL = "https://news.ycombinator.com/item?id={}"
# Recent whoishiring stories searched for the THREADS hiring threads.
THREAD_SEARCH_HITS = 10
MAX_TOKENS = 8000
THREAD_TITLE = "Ask HN: Who is hiring?"
# Monthly threads read, newest first; the latest one is thin early in the month.
THREADS = 2
POSTS_PER_CALL = 25
CALL_CONCURRENCY = 4
# Threads read within this long are served from memory.
CACHE_SECONDS = 60 * 60

_cache: list[tuple[float, list["HiringPost"]]] = []
_http = httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})
_cache_lock = threading.Lock()


@dataclass
class HiringPost:
    id: str
    text: str
    posted_at: datetime


def recent_posts(http: httpx.Client | None = None) -> list[HiringPost]:
    """Top-level posts of the latest 'Ask HN: Who is hiring?' threads, read through HN's public Algolia API."""
    http = http or _http
    res = http.get(f"{API}/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": str(THREAD_SEARCH_HITS)})
    res.raise_for_status()
    threads = [hit["objectID"] for hit in res.json()["hits"] if hit["title"].startswith(THREAD_TITLE)][:THREADS]

    def thread_posts(thread: str) -> list[HiringPost]:
        item = http.get(f"{API}/items/{thread}")
        item.raise_for_status()
        return [
            HiringPost(str(child["id"]), html_to_text(child["text"]), datetime.fromisoformat(child["created_at"]))
            for child in item.json()["children"]
            if child.get("text")
        ]

    with ContextThreadPool(max_workers=THREADS) as pool:
        return [post for posts in pool.map(thread_posts, threads) for post in posts]


def extract_jobs(client: Any, model: str, posts: list[HiringPost]) -> list[Posting]:
    """
    Lists the roles in each post, POSTS_PER_CALL posts per call with calls run in
    parallel. A batch that fails is skipped, so its posts are read again next time.
    """
    batches = [posts[i : i + POSTS_PER_CALL] for i in range(0, len(posts), POSTS_PER_CALL)]
    with ContextThreadPool(max_workers=CALL_CONCURRENCY) as pool:
        found = list(pool.map(lambda batch: _extract(client, model, batch), batches))
    return [posting for postings in found for posting in postings]


def _extract(client: Any, model: str, posts: list[HiringPost]) -> list[Posting]:
    try:
        found: HiringJobs = parse(
            client,
            model=model,
            max_tokens=MAX_TOKENS,
            system=EXTRACTION_SYSTEM,
            content=extraction_message([post.text for post in posts]),
            output_format=HiringJobs,
            error=RuntimeError,
            failure="Reading hiring posts",
        )
    except Exception as error:
        logger.warning("reading hiring posts failed: %s", error)
        return []

    roles: dict[int, int] = {}
    postings = []
    for job in found.jobs:
        if not 0 <= job.post < len(posts) or not job.company.strip() or not job.title.strip():
            continue
        post = posts[job.post]
        roles[job.post] = roles.get(job.post, 0) + 1
        postings.append(
            Posting(
                source="hackernews",
                board=re.sub(r"[^a-z0-9]+", "-", job.company.lower()).strip("-") or "unknown",
                external_id=f"{post.id}-{roles[job.post]}",
                title=job.title.strip(),
                company=job.company.strip(),
                location=job.location,
                url=POST_URL.format(post.id),
                description=post.text,
                posted_at=post.posted_at,
                workplace_type=job.workplace_type,
            )
        )
    return postings


def post_id(posting: Posting) -> str:
    """The Hacker News post a role was read from."""
    return posting.external_id.split("-")[0]


def cached_recent_posts() -> list[HiringPost]:
    """recent_posts, reused for CACHE_SECONDS."""
    with _cache_lock:
        if _cache and time.monotonic() - _cache[0][0] < CACHE_SECONDS:
            return _cache[0][1]
    posts = recent_posts()
    with _cache_lock:
        _cache[:] = [(time.monotonic(), posts)]
    return posts
