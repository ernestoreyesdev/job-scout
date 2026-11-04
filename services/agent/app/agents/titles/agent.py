from typing import Any

from app.agents.schemas import RelatedTitles, Usage
from app.agents.titles.prompts import TITLES_SYSTEM, titles_message

MAX_TITLES = 40
MAX_TITLE_LENGTH = 80


class TitlesError(Exception):
    pass


def related_titles(client: Any, model: str, keywords: list[str], usage: Usage) -> list[str]:
    """One call that turns search keywords into the job titles they cover, deduplicated without case."""
    response = client.beta.messages.parse(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=TITLES_SYSTEM,
        messages=[{"role": "user", "content": titles_message(keywords, MAX_TITLES)}],
        output_format=RelatedTitles,
    )
    usage.add(response.usage)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise TitlesError(f"Finding related job titles failed (stop reason: {response.stop_reason}).")

    titles: dict[str, str] = {}
    for title in response.parsed_output.titles:
        clean = " ".join(title.split())
        if clean and len(clean) <= MAX_TITLE_LENGTH:
            titles.setdefault(clean.lower(), clean)
    return list(titles.values())[:MAX_TITLES]
