from dataclasses import dataclass, field
from typing import Any

from app.agents.discovery.prompts import (
    DISCOVERY_SYSTEM,
    NAMING_SYSTEM,
    company_search_message,
    discovery_message,
    naming_message,
)
from app.agents.schemas import CompanyName, CompanyNames, Usage
from app.sources import board_from_url, board_hosts
from app.sources.base import SourceName


@dataclass
class FoundBoard:
    """A job board seen in web search results, with the titles of the result pages that pointed to it."""

    source: SourceName
    board: str
    titles: list[str] = field(default_factory=list)


def discover_boards(
    client: Any,
    model: str,
    keywords: list[str],
    workplace_types: list[str],
    location: str | None,
    usage: Usage,
    searches: int = 3,
) -> list[FoundBoard]:
    """
    Web searches restricted to the job boards' own sites. Each result URL names
    its company's board, so the boards come from the URLs and not from Claude's reply.
    """
    return search_boards(client, model, discovery_message(keywords, workplace_types, location, searches), searches, usage)


def search_boards(client: Any, model: str, message: str, searches: int, usage: Usage) -> list[FoundBoard]:
    """Runs a web search limited to job board sites and returns the boards its result URLs belong to, in order."""
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
                "allowed_domains": board_hosts(),
            }
        ],
        messages=[{"role": "user", "content": message}],
    )
    usage.add(response.usage)

    found: dict[tuple[SourceName, str], FoundBoard] = {}
    for block in response.content:
        if block.type != "web_search_tool_result" or not isinstance(block.content, list):
            continue
        for result in block.content:
            board = board_from_url(result.url)
            if not board:
                continue
            entry = found.setdefault(board, FoundBoard(*board))
            title = getattr(result, "title", None)
            if title and title not in entry.titles:
                entry.titles.append(title)
    return list(found.values())


def find_company_boards(client: Any, model: str, company: str, usage: Usage, searches: int = 2) -> list[FoundBoard]:
    """Web searches for one company's job board on any of the job systems."""
    return search_boards(client, model, company_search_message(company, searches), searches, usage)


def name_companies(
    client: Any, model: str, boards: list[FoundBoard], usage: Usage
) -> dict[tuple[str, str], CompanyName]:
    """
    One small call that reads each board's search result titles and returns the
    company's name and kind, e.g. 'CVS Health', an employer, for
    cvshealth.wd1/cvs_health_careers.
    """
    if not boards:
        return {}
    response = client.beta.messages.parse(
        model=model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=NAMING_SYSTEM,
        messages=[{"role": "user", "content": naming_message(boards)}],
        output_format=CompanyNames,
    )
    usage.add(response.usage)
    if response.parsed_output is None:
        return {}

    keys = {f"{b.source}/{b.board}": (b.source, b.board) for b in boards}
    return {
        keys[entry.board]: entry.model_copy(update={"name": entry.name.strip()})
        for entry in response.parsed_output.companies
        if entry.board in keys and entry.name.strip()
    }
