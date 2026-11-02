from typing import Any

from app.agents.gap_analysis.prompts import GAP_SYSTEM, gap_message
from app.agents.schemas import GapAnalysis, Usage
from app.sources.base import Posting


class GapAnalysisError(Exception):
    pass


def analyze_gaps(client: Any, model: str, resume_text: str, posting: Posting, usage: Usage) -> GapAnalysis:
    """One call that sorts the job's requirements into covered, weak and missing against the resume."""
    response = client.beta.messages.parse(
        model=model,
        max_tokens=8000,
        output_config={"effort": "low"},
        system=GAP_SYSTEM,
        messages=[{"role": "user", "content": gap_message(resume_text, posting)}],
        output_format=GapAnalysis,
    )
    usage.add(response.usage)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise GapAnalysisError(f"Gap analysis failed (stop reason: {response.stop_reason}).")
    return response.parsed_output
