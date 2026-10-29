import re
from typing import Any
from urllib.parse import urlparse

from app.agents.discovery.prompts import DISCOVERY_SYSTEM, discovery_message
from app.agents.schemas import Usage
from app.sources.base import SourceName

BOARD_HOSTS: dict[str, SourceName] = {
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
}
BOARD_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NOT_BOARDS = {"embed", "job-openings", "jobs"}


def discover_boards(
    client: Any,
    model: str,
    keywords: list[str],
    workplace_types: list[str],
    location: str | None,
    usage: Usage,
    searches: int = 3,
) -> list[tuple[SourceName, str]]:
    """
    Web searches restricted to the job boards' own sites. Each result URL names
    its company's board, so the boards come from the URLs and not from Claude's reply.
    """
    response = client.messages.create(
        model=model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=DISCOVERY_SYSTEM,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": searches,
                "allowed_domains": list(BOARD_HOSTS),
            }
        ],
        messages=[{"role": "user", "content": discovery_message(keywords, workplace_types, location, searches)}],
    )
    usage.add(response.usage)

    boards: list[tuple[SourceName, str]] = []
    for block in response.content:
        if block.type != "web_search_tool_result" or not isinstance(block.content, list):
            continue
        for result in block.content:
            board = board_from_url(result.url)
            if board and board not in boards:
                boards.append(board)
    return boards


def board_from_url(url: str) -> tuple[SourceName, str] | None:
    """('greenhouse', 'gusto') from https://job-boards.greenhouse.io/gusto/jobs/123; None for other URLs."""
    parsed = urlparse(url)
    source = BOARD_HOSTS.get(parsed.hostname or "")
    slug = parsed.path.strip("/").split("/")[0].lower()
    if source is None or not BOARD_SLUG.match(slug) or slug in NOT_BOARDS:
        return None
    return source, slug
