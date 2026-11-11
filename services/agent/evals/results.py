"""Saves an evaluation run's results to eval_runs, where the admin page shows them over time."""

from typing import Any

from app.db import Rest


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
