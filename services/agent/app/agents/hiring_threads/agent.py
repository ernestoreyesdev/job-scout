import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.agents.hiring_threads.prompts import EXTRACTION_SYSTEM, extraction_message
from app.agents.schemas import HiringJobs, Usage
from app.sources.base import Posting
from app.sources.text import html_to_text
from app.telemetry import ContextThreadPool

logger = logging.getLogger("agent")

API = "https://hn.algolia.com/api/v1"
THREAD_TITLE = "Ask HN: Who is hiring?"
# Monthly threads read, newest first; the latest one is thin early in the month.
THREADS = 2
POSTS_PER_CALL = 25
CALL_CONCURRENCY = 4


@dataclass
class HiringPost:
    id: str
    text: str
    posted_at: datetime


def recent_posts(http: httpx.Client | None = None) -> list[HiringPost]:
    """Top-level posts of the latest 'Ask HN: Who is hiring?' threads, read through HN's public Algolia API."""
    http = http or httpx.Client(timeout=30, headers={"User-Agent": "job-finder"})
    res = http.get(f"{API}/search_by_date", params={"tags": "story,author_whoishiring", "hitsPerPage": "10"})
    res.raise_for_status()
    threads = [hit["objectID"] for hit in res.json()["hits"] if hit["title"].startswith(THREAD_TITLE)][:THREADS]
    posts = []
    for thread in threads:
        item = http.get(f"{API}/items/{thread}")
        item.raise_for_status()
        posts += [
            HiringPost(str(child["id"]), html_to_text(child["text"]), datetime.fromisoformat(child["created_at"]))
            for child in item.json()["children"]
            if child.get("text")
        ]
    return posts


def extract_jobs(client: Any, model: str, posts: list[HiringPost], usage: Usage) -> list[Posting]:
    """
    Lists the roles in each post, POSTS_PER_CALL posts per call with calls run in
    parallel. A batch that fails is skipped, so its posts are read again next time.
    """
    batches = [posts[i : i + POSTS_PER_CALL] for i in range(0, len(posts), POSTS_PER_CALL)]
    spent = [Usage() for _ in batches]
    with ContextThreadPool(max_workers=CALL_CONCURRENCY) as pool:
        found = list(pool.map(lambda batch, used: _extract(client, model, batch, used), batches, spent))
    for batch_usage in spent:
        usage.add(batch_usage)
    return [posting for postings in found for posting in postings]


def _extract(client: Any, model: str, posts: list[HiringPost], usage: Usage) -> list[Posting]:
    try:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=8000,
            output_config={"effort": "low"},
            system=EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": extraction_message([post.text for post in posts])}],
            output_format=HiringJobs,
        )
    except Exception as error:
        logger.warning("reading hiring posts failed: %s", error)
        return []
    usage.add(response.usage)
    if response.parsed_output is None:
        return []

    roles: dict[int, int] = {}
    postings = []
    for job in response.parsed_output.jobs:
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
                url=f"https://news.ycombinator.com/item?id={post.id}",
                description=post.text,
                posted_at=post.posted_at,
                workplace_type=job.workplace_type,
            )
        )
    return postings
