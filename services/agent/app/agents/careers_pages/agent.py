import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.agents.careers_pages.prompts import SEARCH_SYSTEM, search_message
from app.agents.schemas import Usage
from app.sources import board_hosts

logger = logging.getLogger("agent")

# Statuses that mean the page isn't there; others, like 403 from sites that block scripts, still count.
MISSING_STATUSES = frozenset({404, 410})
CAREERS_PATH = re.compile(r"career|jobs|join|work-with|opportunit", re.I)


def page_loads(url: str, http: httpx.Client) -> bool:
    """True when the URL answers with a page that exists, following redirects."""
    if urlparse(url).scheme not in ("http", "https"):
        return False
    try:
        res = http.get(url, follow_redirects=True)
    except httpx.HTTPError:
        return False
    return res.status_code not in MISSING_STATUSES and res.status_code < 500


def search_careers_page(client: Any, model: str, company: str, usage: Usage) -> str | None:
    """One web search that leaves out job board sites; the first result that looks like a careers page wins."""
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=SEARCH_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1, "blocked_domains": board_hosts()}],
        messages=[{"role": "user", "content": search_message(company)}],
    )
    usage.add(response.usage)
    urls = [
        result.url
        for block in response.content
        if block.type == "web_search_tool_result" and isinstance(block.content, list)
        for result in block.content
    ]
    return next((url for url in urls if CAREERS_PATH.search(urlparse(url).path + urlparse(url).netloc)), None)


def find_careers_page(
    client: Any, model: str, company: str, suggestion: str | None, usage: Usage, http: httpx.Client
) -> str | None:
    """The suggested careers page when it loads; otherwise the result of one web search, or None."""
    if suggestion and page_loads(suggestion, http):
        return suggestion
    try:
        return search_careers_page(client, model, company, usage)
    except Exception as error:
        logger.warning("careers page search for %s failed: %s", company, error)
        return None
