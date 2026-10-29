from typing import Any

from app.agents.schemas import Shortlist, Usage
from app.agents.triage.prompts import TRIAGE_SYSTEM, triage_blocks
from app.sources.base import Posting

# Postings sent to triage at most, newest first; titles are short, so this stays a few thousand tokens.
MAX_CANDIDATES = 300


class TriageError(Exception):
    pass


def shortlist(client: Any, model: str, resume_text: str, postings: list[Posting], count: int, usage: Usage) -> list[int]:
    """
    One call that reads the postings' titles next to the resume and returns the
    indexes of the `count` most promising, best first. Indexes refer to `postings`.
    """
    candidates = postings[:MAX_CANDIDATES]
    response = client.beta.messages.parse(
        model=model,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=TRIAGE_SYSTEM,
        messages=[{"role": "user", "content": triage_blocks(resume_text, candidates, count)}],
        output_format=Shortlist,
    )
    usage.add(response.usage)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise TriageError(f"Shortlisting failed (stop reason: {response.stop_reason}).")

    picked: list[int] = []
    for index in response.parsed_output.ids:
        if 0 <= index < len(candidates) and index not in picked:
            picked.append(index)
    return picked
