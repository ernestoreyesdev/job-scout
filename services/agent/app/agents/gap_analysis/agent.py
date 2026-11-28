from typing import Any

from app.agents.claude import parse
from app.agents.gap_analysis.prompts import GAP_STEP, GAP_SYSTEM, gap_message
from app.agents.schemas import GapAnalysis
from app.sources.base import Posting

MAX_TOKENS = 8000


class GapAnalysisError(Exception):
    pass


def analyze_gaps(client: Any, model: str, resume_text: str, posting: Posting) -> GapAnalysis:
    """One call that sorts the job's requirements into covered, weak and missing against the resume."""
    return parse(
        client,
        model=model,
        max_tokens=MAX_TOKENS,
        step=GAP_STEP,
        system=GAP_SYSTEM,
        content=gap_message(resume_text, posting),
        output_format=GapAnalysis,
        error=GapAnalysisError,
        failure="Gap analysis",
    )
