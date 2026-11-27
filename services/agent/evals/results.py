"""Saves an evaluation run's results to eval_runs, where the admin page shows them over time."""

from collections import Counter
from typing import Any

import anthropic

from app.agents.schemas import Usage
from app.db import Rest
from app.sources.base import Posting, SourceName
from app.telemetry import CallLog, RecordingClient

# Haiku 5.5 prices per million tokens: input, output, cache read, cache write.
PRICES = (0.10, 0.50, 0.01, 0.125)
# Claude calls an eval makes at once.
EVAL_CONCURRENCY = 4


def save_result(
    service: Rest,
    eval_name: str,
    metrics: dict[str, Any],
    cost: float | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> None:
    service.insert(
        "eval_runs",
        {"eval": eval_name, "metrics": metrics, "cost": cost, "model": model, "prompt_version": prompt_version},
        select="id",
    )


def usage_cost(usage: Usage) -> float:
    """Dollars for a run's tokens at PRICES."""
    tokens = (usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.cache_creation_input_tokens)
    return sum(n * price / 1_000_000 for n, price in zip(tokens, PRICES, strict=True))


def print_cost(usage: Usage) -> None:
    """Prints a run's cost at PRICES and its token counts."""
    print(f"Cost: ${usage_cost(usage):.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")


def skip(service: Rest, eval_name: str, message: str) -> None:
    """Prints why the eval didn't run and records it, so the admin page shows the same text."""
    print(message)
    save_result(service, eval_name, {"skipped": message})


def busiest_account(service: Rest, rows: list[dict[str, Any]]) -> tuple[str, str] | None:
    """The user with the most of `rows` among those with primary resume text, and that text; None when there is none."""
    resumes = {
        row["user_id"]: row["text"]
        for row in service.select("resumes", {"select": "user_id,text", "is_primary": "eq.true", "text": "not.is.null"})
    }
    counts = Counter(row["user_id"] for row in rows if row["user_id"] in resumes)
    if not counts:
        return None
    user_id = counts.most_common(1)[0][0]
    return user_id, resumes[user_id]


def eval_client(api_key: str) -> tuple[RecordingClient, CallLog]:
    """A Claude client whose calls are logged for the eval's cost line."""
    calls = CallLog()
    return RecordingClient(anthropic.Anthropic(api_key=api_key), calls), calls


def eval_posting(
    external_id: str, title: str, company: str, location: str | None, description: str, source: SourceName = "manual"
) -> Posting:
    """A posting built from eval data, with placeholder board, link and date."""
    return Posting(
        source=source,
        board="eval",
        external_id=external_id,
        title=title,
        company=company,
        location=location,
        url="https://example.com",
        description=description,
        posted_at=None,
    )
