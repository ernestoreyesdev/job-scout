"""
Measures whether labeled examples improve fit scores: `uv run python -m
evals.labels.run`. Takes the account with the most good/bad labels and a
primary resume, holds out a third of each label, and scores the held-out jobs
three times with the same call a search makes: without examples, with the most
recent examples, and with the examples nearest the held-out batch by embedding,
all drawn only from the rest. A run costs about three scoring calls per
held-out job. Point it at the hosted project by setting SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY for that project, plus ANTHROPIC_API_KEY or that
project's AGENT_ENCRYPTION_KEY to use the account's saved key.
"""

from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anthropic
import numpy as np

from app.agents.orchestrator import MAX_EXAMPLES, MIN_EXAMPLES, labeled_job
from app.agents.schemas import FitScore, Usage
from app.agents.scoring.agent import score_posting
from app.agents.scoring.prompts import FIT_SYSTEM, LabeledJob
from app.config import get_settings
from app.crypto import decrypt
from app.db import service_db
from app.embeddings import embed_jobs, job_text
from app.sources.base import Posting
from app.telemetry import prompt_version
from evals.results import save_result

CUTS = (50, 60, 70, 80)
HOLD_OUT_EVERY = 3
MIN_HELD_OUT = 2
# Haiku 5.5 prices per million tokens: input, output, cache read, cache write.
PRICES = (0.10, 0.50, 0.01, 0.125)


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Every third job of each label, in posting id order, is held out; the rest can be examples."""
    train: list[dict] = []
    held: list[dict] = []
    for label in ("good", "bad"):
        group = sorted((row for row in rows if row["fit_label"] == label), key=lambda row: row["posting_id"])
        for i, row in enumerate(group):
            (held if i % HOLD_OUT_EVERY == 0 else train).append(row)
    return train, held


def examples_from(train: list[dict]) -> list[LabeledJob]:
    """The most recently updated MAX_EXAMPLES of each label, as live scoring picks them."""
    picked: list[LabeledJob] = []
    for label in ("good", "bad"):
        group = sorted((row for row in train if row["fit_label"] == label), key=lambda row: row["updated_at"], reverse=True)
        picked += [labeled_job(label, row["posting"]) for row in group[:MAX_EXAMPLES]]
    return picked


def closest_from(train: list[dict], held: list[dict]) -> list[LabeledJob]:
    """Up to MAX_EXAMPLES of each label nearest the average embedding of the held-out jobs, as live scoring picks them."""
    def vectors(rows: list[dict]) -> np.ndarray:
        texts = [job_text(r["posting"]["title"], r["posting"]["company"], r["posting"]["location"], r["posting"]["description"]) for r in rows]
        found = np.array(embed_jobs(texts), dtype=np.float32)
        return found / np.linalg.norm(found, axis=1, keepdims=True)

    anchor = vectors(held).mean(axis=0)
    anchor /= np.linalg.norm(anchor)
    similarity = vectors(train) @ anchor
    picked: list[LabeledJob] = []
    for label in ("good", "bad"):
        group = sorted((i for i, row in enumerate(train) if row["fit_label"] == label), key=lambda i: -similarity[i])
        picked += [labeled_job(label, train[i]["posting"]) for i in group[:MAX_EXAMPLES]]
    return picked


def auc(scored: Sequence[tuple[str, float]]) -> float:
    """Chance that a random good job outscores a random bad one; ties count half."""
    good = [score for label, score in scored if label == "good"]
    bad = [score for label, score in scored if label == "bad"]
    wins = sum(1.0 if g > b else 0.5 if g == b else 0.0 for g in good for b in bad)
    return wins / (len(good) * len(bad))


def report(name: str, scored: list[tuple[str, int]]) -> dict[str, Any]:
    """Prints one arm's results and returns them: mean scores, AUC, and precision and recall per cut."""
    good = [score for label, score in scored if label == "good"]
    bad = [score for label, score in scored if label == "bad"]
    result: dict[str, Any] = {"mean_good": sum(good) / len(good), "mean_bad": sum(bad) / len(bad), "auc": auc(scored), "cuts": {}}
    print(f"\n{name}")
    print(f"  mean score: good {result['mean_good']:.1f}, bad {result['mean_bad']:.1f}   AUC {result['auc']:.2f}")
    for cut in CUTS:
        tp = sum(1 for label, score in scored if score >= cut and label == "good")
        fp = sum(1 for label, score in scored if score >= cut and label == "bad")
        precision = tp / (tp + fp) if tp + fp else None
        result["cuts"][str(cut)] = {"precision": precision, "recall": tp / len(good)}
        print(f"  cut {cut}: precision {'-' if precision is None else f'{precision:.0%}':>4}, recall {tp / len(good):.0%}")
    return result


def main() -> None:
    settings = get_settings()
    db = service_db(settings)
    labeled = db.select("applications", {"select": "user_id", "fit_label": "not.is.null"})
    resumes = {
        row["user_id"]: row["text"]
        for row in db.select("resumes", {"select": "user_id,text", "is_primary": "eq.true", "text": "not.is.null"})
    }
    counts = Counter(row["user_id"] for row in labeled if row["user_id"] in resumes)
    if not counts:
        print("No account has both labeled jobs and a primary resume.")
        save_result(db, "labels", {"skipped": "No account has both rated jobs and a primary resume."})
        return
    user_id = counts.most_common(1)[0][0]
    credentials = db.select(
        "api_credentials", {"select": "ciphertext", "user_id": f"eq.{user_id}", "provider": "eq.anthropic"}
    )
    # A key passed in ANTHROPIC_API_KEY wins, so a saved key encrypted elsewhere never needs decrypting.
    api_key = settings.anthropic_api_key or (decrypt(credentials[0]["ciphertext"], settings.agent_encryption_key) if credentials else None)
    if not api_key:
        print("That account has no Anthropic key and ANTHROPIC_API_KEY is not set.")
        return

    rows = [
        row
        for row in db.select(
            "applications",
            {"select": "posting_id,fit_label,updated_at,posting:postings(*)", "user_id": f"eq.{user_id}", "fit_label": "not.is.null"},
        )
        if row["posting"]["description"]
    ]
    train, held = split(rows)
    have = {label: (sum(r["fit_label"] == label for r in train), sum(r["fit_label"] == label for r in held)) for label in ("good", "bad")}
    print(f"{len(rows)} labeled jobs with text: " + ", ".join(f"{label} {t} examples / {h} held out" for label, (t, h) in have.items()))
    if any(t < MIN_EXAMPLES or h < MIN_HELD_OUT for t, h in have.values()):
        print(f"Need at least {MIN_EXAMPLES + MIN_HELD_OUT} jobs with text per label. Mark more jobs good and bad, then rerun.")
        save_result(db, "labels", {"skipped": f"Needs at least {MIN_EXAMPLES + MIN_HELD_OUT} rated jobs of each kind."})
        return

    client = anthropic.Anthropic(api_key=api_key)
    resume = resumes[user_id]
    examples = examples_from(train)
    closest = closest_from(train, held)
    if {(e.label, e.title, e.company) for e in closest} == {(e.label, e.title, e.company) for e in examples}:
        print(f"Neither label has more than {MAX_EXAMPLES} jobs to pick from, so recent and closest pick the same jobs.")
    usage = Usage()

    def score(row: dict, with_examples: list[LabeledJob]) -> tuple[str, int, object]:
        fit, call_usage = score_posting(
            client, settings.scoring_model, settings.scoring_effort, resume, Posting.model_validate(row["posting"]), with_examples
        )
        return row["fit_label"], fit.score, call_usage

    results: dict[str, Any] = {}
    arms = (("Without examples", []), (f"With {len(examples)} recent examples", examples), (f"With {len(closest)} closest examples", closest))
    for name, with_examples in arms:
        # The first call runs alone so the cached prefix exists before the rest.
        first = score(held[0], with_examples)
        with ThreadPoolExecutor(max_workers=4) as pool:
            calls = [first, *pool.map(score, held[1:], [with_examples] * (len(held) - 1))]
        for *_, call_usage in calls:
            usage.add(call_usage)
        results[name] = report(name, [(label, value) for label, value, _ in calls])
    cost = sum(
        n * price / 1_000_000
        for n, price in zip(
            (usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.cache_creation_input_tokens),
            PRICES,
        )
    )
    print(f"\nCost: ${cost:.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")
    save_result(
        db,
        "labels",
        {"held_out": len(held), "arms": results},
        cost,
        settings.scoring_model,
        prompt_version(FIT_SYSTEM, FitScore),
    )


if __name__ == "__main__":
    main()
