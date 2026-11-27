from typing import Any

from app.agents.claude import parse
from app.agents.schemas import RelatedTitles
from app.agents.titles.prompts import TITLES_SYSTEM, titles_message

MAX_TITLES = 40
MAX_TITLE_LENGTH = 80
MAX_TOKENS = 2000


class TitlesError(Exception):
    pass


def related_titles(client: Any, model: str, keywords: list[str]) -> list[str]:
    """One call that turns search keywords into the job titles they cover, deduplicated without case."""
    related = parse(
        client,
        model=model,
        max_tokens=MAX_TOKENS,
        system=TITLES_SYSTEM,
        content=titles_message(keywords, MAX_TITLES),
        output_format=RelatedTitles,
        error=TitlesError,
        failure="Finding related job titles",
    )

    titles: dict[str, str] = {}
    for title in related.titles:
        clean = " ".join(title.split())
        if clean and len(clean) <= MAX_TITLE_LENGTH:
            titles.setdefault(clean.lower(), clean)
    return list(titles.values())[:MAX_TITLES]
