from typing import Any

from app.agents.claude import parse
from app.agents.follow_up.prompts import FOLLOW_UP_SYSTEM, follow_up_message
from app.agents.schemas import FollowUpDraft


class FollowUpError(Exception):
    pass


def draft_follow_up(client: Any, model: str, resume_text: str, title: str, company: str, applied_on: str) -> FollowUpDraft:
    """One call that drafts a follow-up email for the candidate to review and send."""
    return parse(
        client,
        model=model,
        max_tokens=2000,
        system=FOLLOW_UP_SYSTEM,
        content=follow_up_message(resume_text, title, company, applied_on),
        output_format=FollowUpDraft,
        error=FollowUpError,
        failure="Drafting",
    )
