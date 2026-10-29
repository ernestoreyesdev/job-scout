import json
from collections.abc import Callable
from typing import Any

from app.agents.schemas import FitScore, Usage
from app.agents.scoring.prompts import FIT_SYSTEM, fit_message
from app.db import Rest
from app.sources.base import Posting
from app.sources.filters import matches_keywords

# Refusals are rerouted server-side by category instead of failing the call.
FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]

TOOLS = [
    {
        "name": "search_jobs",
        "description": (
            "Fetch a company's open postings, keep those whose title or location matches any keyword, "
            "and return up to `limit` of them with their posting ids."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company name, e.g. 'Stripe'."},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
            "required": ["company", "keywords", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "name": "score_fit",
        "description": "Score how well the user's resume fits one posting (0-100) with strengths and gaps.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"posting_id": {"type": "string"}},
            "required": ["posting_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "track_application",
        "description": "Save a scored posting to the user's tracker. Call score_fit for the posting first.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"posting_id": {"type": "string"}},
            "required": ["posting_id"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    """A failure reported back to the model as an is_error tool result."""


class SearchTools:
    """
    Executes the search run's tools. Postings are written with the service
    role; the tracker row is written with the user's token so RLS applies.
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        finder: Callable[[str], list[Posting]],
        company: str,
        max_results: int,
        resume_id: str,
        resume_text: str,
        user_id: str,
        user: Rest,
        service: Rest,
        usage: Usage,
        report: Callable[[str], None],
    ):
        self.client = client
        self.model = model
        self.finder = finder
        self.company = company
        self.max_results = max_results
        self.resume_id = resume_id
        self.resume_text = resume_text
        self.user_id = user_id
        self.user = user
        self.service = service
        self.usage = usage
        self.report = report
        self.postings: dict[str, Posting] = {}
        self.scores: dict[str, FitScore] = {}
        self.tracked: set[str] = set()

    def run(self, name: str, tool_input: dict[str, Any]) -> str:
        handlers: dict[str, Callable[..., str]] = {
            "search_jobs": self.search_jobs,
            "score_fit": self.score_fit,
            "track_application": self.track_application,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"Unknown tool: {name}")
        return handler(**tool_input)

    def search_jobs(self, company: str, keywords: list[str], limit: int) -> str:
        if company.strip().lower() != self.company.strip().lower():
            raise ToolError(f"Only the requested company '{self.company}' can be searched.")

        self.report(f"Finding {self.company}'s open jobs…")
        everything = self.finder(self.company)
        matched = [p for p in everything if matches_keywords(p, keywords)]
        found = matched[: min(limit, self.max_results)]
        self.report(f"Found {len(everything)} open jobs, {len(matched)} match. Scoring {len(found)}.")
        if not found:
            return "No postings matched."

        rows = self.service.insert(
            "postings",
            [p.model_dump(mode="json") for p in found],
            on_conflict="source,external_id",
        )
        by_external_id = {p.external_id: p for p in found}
        listing = []
        for row in rows:
            self.postings[row["id"]] = by_external_id[row["external_id"]]
            listing.append({"posting_id": row["id"], "title": row["title"], "location": row["location"]})

        return f"<job>\n{json.dumps(listing)}\n</job>"

    def score_fit(self, posting_id: str) -> str:
        posting = self.postings.get(posting_id)
        if posting is None:
            raise ToolError("Unknown posting_id; use an id returned by search_jobs.")

        self.report(f"Scoring {len(self.scores) + 1} of {len(self.postings)}: {posting.title}")
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            betas=FALLBACK_BETAS,
            fallbacks="default",
            output_config={"effort": "medium"},
            system=FIT_SYSTEM,
            messages=[{"role": "user", "content": fit_message(self.resume_text, posting)}],
            output_format=FitScore,
        )
        self.usage.add(response.usage)
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ToolError(f"Scoring failed (stop reason: {response.stop_reason}).")

        fit = response.parsed_output
        self.scores[posting_id] = fit
        return json.dumps({"posting_id": posting_id, "score": fit.score})

    def track_application(self, posting_id: str) -> str:
        fit = self.scores.get(posting_id)
        if fit is None:
            raise ToolError("Score this posting with score_fit before tracking it.")

        self.user.insert(
            "applications",
            {
                "user_id": self.user_id,
                "posting_id": posting_id,
                "resume_id": self.resume_id,
                "fit_score": fit.score,
                "fit_summary": fit.summary,
                "strengths": fit.strengths,
                "gaps": fit.gaps,
            },
            on_conflict="user_id,posting_id",
        )
        self.tracked.add(posting_id)
        self.report(f"Saved {len(self.tracked)} of {len(self.postings)} to your tracker.")
        return "Tracked."
