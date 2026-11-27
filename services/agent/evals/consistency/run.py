"""
Measures how much fit scores vary when the same job is scored again: `uv run
python -m evals.consistency.run`. Takes the account with the most scored jobs
and a primary resume, picks JOBS of them spread across the score range, and
scores each REPEATS times with the call a search makes, without labeled
examples or lessons, then REPEATS times more as a search saves it, averaging
scores near a fit label's cut. Reports each job's spread (highest minus lowest
score) and how many jobs land on both sides of a cut, for single scores and
saved ones. A run makes up to JOBS x REPEATS x 4 Claude Haiku calls. Needs ANTHROPIC_API_KEY, plus SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY for the project to read from and save to.
"""

import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anthropic

from app.agents.orchestrator import with_edits
from app.agents.schemas import FitScore
from app.agents.scoring.agent import SCORE_CUTS, score_posting, steady_score
from app.agents.scoring.prompts import FIT_SYSTEM
from app.config import get_settings
from app.db import service_db
from app.telemetry import CallLog, RecordingClient, prompt_version
from evals.results import EVAL_CONCURRENCY, save_result, usage_cost

JOBS = 10
REPEATS = 5


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("Set ANTHROPIC_API_KEY to the key the eval should use.")
        sys.exit(1)
    db = service_db(settings)
    resumes = {
        row["user_id"]: row["text"]
        for row in db.select("resumes", {"select": "user_id,text", "is_primary": "eq.true", "text": "not.is.null"})
    }
    scored = db.select("applications", {"select": "user_id", "fit_score": "not.is.null"})
    counts = Counter(row["user_id"] for row in scored if row["user_id"] in resumes)
    if not counts:
        print("No account has both scored jobs and a primary resume.")
        save_result(db, "consistency", {"skipped": "No account has both scored jobs and a primary resume."})
        return
    user_id = counts.most_common(1)[0][0]
    rows = db.select(
        "applications",
        {
            "select": "fit_score,edited_title,edited_company,edited_description,posting:postings(*)",
            "user_id": f"eq.{user_id}",
            "fit_score": "not.is.null",
        },
    )
    jobs = spread_out([row for row in rows if row["edited_description"] or row["posting"]["description"]], JOBS)
    if not jobs:
        print("None of that account's scored jobs has a description saved.")
        save_result(db, "consistency", {"skipped": "No scored job has a description saved."})
        return

    calls = CallLog()
    client = RecordingClient(anthropic.Anthropic(api_key=settings.anthropic_api_key), calls)
    resume = resumes[user_id]

    def score(row: dict[str, Any]) -> int:
        return score_posting(client, settings.scoring_model, settings.scoring_effort, resume, with_edits(row)).score

    def steadied(row: dict[str, Any]) -> int:
        return steady_score(score(row), lambda: score(row))

    with ThreadPoolExecutor(max_workers=EVAL_CONCURRENCY) as pool:
        runs = [list(pool.map(score, jobs)) for _ in range(REPEATS)]
        steady_runs = [list(pool.map(steadied, jobs)) for _ in range(REPEATS)]
    results = [
        {
            "title": row["posting"]["title"],
            "saved": row["fit_score"],
            "scores": [run[i] for run in runs],
            "steadied": [run[i] for run in steady_runs],
        }
        for i, row in enumerate(jobs)
    ]

    print(f"{'Job':<48} {'Saved':>5}  {'Single scores':<20}  Averaged near a cut")
    for r in results:
        single = " ".join(f"{s:>3}" for s in r["scores"])
        print(f"{r['title'][:48]:<48} {r['saved']:>5}  {single:<20}  {' '.join(f'{s:>3}' for s in r['steadied'])}")
    single = summarize([r["scores"] for r in results])
    averaged = summarize([r["steadied"] for r in results])
    usage = calls.usage()
    cost = usage_cost(usage)
    metrics = {"jobs": len(results), "repeats": REPEATS, **single, "steadied": averaged, "results": results}
    for name, summary in (("Single scores", single), ("Averaged near a cut", averaged)):
        flips = ", ".join(f"{cut}: {count}" for cut, count in summary["label_flips"].items())
        print(
            f"\n{name}: spread mean {summary['mean_spread']:.1f}, largest {summary['largest_spread']}, "
            f"mean standard deviation {summary['mean_deviation']:.1f}; jobs on both sides of a cut: {flips}"
        )
    print(f"\nCost: ${cost:.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")
    save_result(db, "consistency", metrics, cost, settings.scoring_model, prompt_version(FIT_SYSTEM, FitScore))


def spread_out(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Up to `count` rows evenly spaced through the rows sorted by saved score, so low, middle and high scores all appear."""
    ordered = sorted(rows, key=lambda row: (row["fit_score"], row["posting"]["id"]))
    if len(ordered) <= count:
        return ordered
    step = (len(ordered) - 1) / (count - 1)
    return [ordered[round(i * step)] for i in range(count)]


def summarize(scores: list[list[int]]) -> dict[str, Any]:
    """Spread, standard deviation and cut crossings over each job's repeated scores."""
    spreads = [max(job) - min(job) for job in scores]
    return {
        "mean_spread": statistics.mean(spreads),
        "largest_spread": max(spreads),
        "mean_deviation": statistics.mean(statistics.pstdev(job) for job in scores),
        "label_flips": {str(cut): sum(1 for job in scores if min(job) < cut <= max(job)) for cut in SCORE_CUTS},
    }


if __name__ == "__main__":
    main()
