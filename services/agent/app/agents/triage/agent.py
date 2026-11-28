from typing import Any

from app.agents.claude import parse
from app.agents.schemas import Shortlist
from app.agents.triage.prompts import TRIAGE_STEP, TRIAGE_SYSTEM, triage_blocks
from app.sources.base import Posting

# Postings sent to triage at most, newest first; titles are short, so this stays a few thousand tokens.
MAX_CANDIDATES = 300
MAX_TOKENS = 4000


class TriageError(Exception):
    pass


def shortlist(client: Any, model: str, resume_text: str, postings: list[Posting], count: int) -> list[int]:
    """
    One call that reads the postings' titles next to the resume and returns the
    indexes of the `count` most promising, best first. Indexes refer to `postings`.
    """
    candidates = postings[:MAX_CANDIDATES]
    chosen = parse(
        client,
        model=model,
        max_tokens=MAX_TOKENS,
        step=TRIAGE_STEP,
        system=TRIAGE_SYSTEM,
        content=triage_blocks(resume_text, candidates, count),
        output_format=Shortlist,
        error=TriageError,
        failure="Shortlisting",
    )

    picked: list[int] = []
    for index in chosen.ids:
        if 0 <= index < len(candidates) and index not in picked:
            picked.append(index)
    return picked
