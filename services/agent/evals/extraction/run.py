"""
Scores the extraction of posting facts against labels.json: `uv run python -m
evals.extraction.run`. Each posting goes through the same scoring call a search
makes, with the primary resume of the first account that has an Anthropic key, so a run
costs about as much as scoring that many jobs. Run `evals.extraction.export`
first to write the posting text.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from app.agents.schemas import JobDetails, Usage
from app.agents.scoring.agent import score_posting
from app.config import get_settings
from app.crypto import decrypt
from app.db import service_db
from app.sources.base import Posting

HERE = Path(__file__).parent
EXACT_FIELDS = ("salary_currency", "salary_period", "clearance", "visa_sponsorship", "years_experience", "workplace_type")
SALARY_TOLERANCE = 0.01
# Haiku 5.5 prices per million tokens: input, output, cache read, cache write.
PRICES = (0.10, 0.50, 0.01, 0.125)


def same(field: str, expected: object, actual: object) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if field.startswith("salary_") and isinstance(expected, int | float):
        return abs(float(actual) - expected) <= abs(expected) * SALARY_TOLERANCE  # pyright: ignore[reportArgumentType]
    if isinstance(expected, str):
        return str(expected).strip().lower() == str(actual).strip().lower()
    return expected == actual


def stack_overlap(expected: list[str], actual: list[str]) -> tuple[int, int, int]:
    """Tools in both lists, only in the extraction, and only in the label, ignoring case."""
    want, got = {t.lower() for t in expected}, {t.lower() for t in actual}
    return len(want & got), len(got - want), len(want - got)


def main() -> None:
    settings = get_settings()
    db = service_db(settings)
    labels = json.loads((HERE / "labels.json").read_text())
    inputs = {(i["source"], i["external_id"]): i for i in json.loads((HERE / "postings.local.json").read_text())}
    credentials = {
        row["user_id"]: row["ciphertext"]
        for row in db.select("api_credentials", {"select": "user_id,ciphertext", "provider": "eq.anthropic"})
    }
    resumes = db.select("resumes", {"select": "user_id,text", "is_primary": "eq.true", "text": "not.is.null"})
    resume = next(row for row in resumes if row["user_id"] in credentials)
    credential = {"ciphertext": credentials[resume["user_id"]]}
    client = anthropic.Anthropic(api_key=decrypt(credential["ciphertext"], settings.agent_encryption_key))

    def extract(label: dict) -> tuple[dict, JobDetails, object]:
        item = inputs[(label["source"], label["external_id"])]
        posting = Posting(
            source=item["source"],
            board="eval",
            external_id=item["external_id"],
            title=item["title"],
            company=item["company"],
            location=item["location"],
            url="https://example.com",
            description=item["text"],
            posted_at=None,
        )
        fit, usage = score_posting(client, settings.scoring_model, settings.scoring_effort, resume["text"], posting)
        return label, fit.details, usage

    # The first call runs alone so the cached resume prefix exists before the rest.
    first = extract(labels[0])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [first, *pool.map(extract, labels[1:])]

    usage = Usage()
    fields = ["salary_min", "salary_max", *EXACT_FIELDS]
    right = {field: 0 for field in fields}
    stated = {field: [0, 0] for field in fields}
    both = extra = missed = 0
    misses: list[str] = []
    for label, details, call_usage in results:
        usage.add(call_usage)
        actual = details.model_dump()
        for field in fields:
            if same(field, label[field], actual[field]):
                right[field] += 1
                if label[field] is not None:
                    stated[field][0] += 1
            else:
                misses.append(f"{label['source']}/{label['external_id']} {field}: expected {label[field]!r}, got {actual[field]!r}")
            if label[field] is not None:
                stated[field][1] += 1
        b, e, m = stack_overlap(label["tech_stack"], details.tech_stack)
        both, extra, missed = both + b, extra + e, missed + m

    total = len(results)
    print(f"{total} postings\n")
    print(f"{'field':<18}{'accuracy':>10}{'when stated':>14}")
    for field in fields:
        found, present = stated[field]
        print(f"{field:<18}{right[field] / total:>10.0%}{(f'{found}/{present}' if present else '-'):>14}")
    precision = both / (both + extra) if both + extra else 0
    recall = both / (both + missed) if both + missed else 0
    print(f"\ntech_stack        precision {precision:.0%}, recall {recall:.0%} ({both} shared, {extra} extra, {missed} missed)")
    cost = sum(
        n * price / 1_000_000
        for n, price in zip(
            (usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.cache_creation_input_tokens),
            PRICES,
        )
    )
    print(f"\nCost: ${cost:.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")
    if misses:
        print("\nMismatches:")
        print("\n".join(f"  {miss}" for miss in misses))


if __name__ == "__main__":
    main()
