"""Saves an evaluation run's results to eval_runs, where the admin page shows them over time."""

from typing import Any

from app.agents.schemas import Usage
from app.db import Rest

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
