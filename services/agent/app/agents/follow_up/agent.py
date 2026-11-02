from typing import Any

from app.agents.follow_up.prompts import FOLLOW_UP_SYSTEM, follow_up_message
from app.agents.schemas import FollowUpDraft, Usage


class FollowUpError(Exception):
    pass


def draft_follow_up(
    client: Any, model: str, resume_text: str, title: str, company: str, applied_on: str, usage: Usage
) -> FollowUpDraft:
    """One call that drafts a follow-up email for the candidate to review and send."""
    response = client.beta.messages.parse(
        model=model,
        max_tokens=2000,
        output_config={"effort": "low"},
        system=FOLLOW_UP_SYSTEM,
        messages=[{"role": "user", "content": follow_up_message(resume_text, title, company, applied_on)}],
        output_format=FollowUpDraft,
    )
    usage.add(response.usage)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise FollowUpError(f"Drafting failed (stop reason: {response.stop_reason}).")
    return response.parsed_output
