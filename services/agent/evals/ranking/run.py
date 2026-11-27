"""
Compares how searches pick which jobs to score: `uv run python -m
evals.ranking.run`. Takes the most recent scored search, matches its rule
against the saved open jobs the way a search does, and builds the scoring pool
twice: once with the Claude title shortlist and once by resume similarity.
Every job in either pool is scored without labeled examples, and each method's
pool is reported by how many reach the min score (DEFAULT_CUT when the search had none).
A run costs about one shortlist call per MAX_CANDIDATES matches plus up to two scoring
calls per job in the pool. Point it at the hosted project by setting
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and ANTHROPIC_API_KEY.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any

import anthropic

from app.agents.orchestrator import (
    MAX_PER_COMPANY,
    POOL_FACTOR,
    by_resume_fit,
    job_key,
    one_per_job,
    one_per_title,
    pick,
    saved_id,
    with_descriptions,
)
from app.agents.schemas import FitScore, SearchRule
from app.agents.scoring.agent import SCORE_CONCURRENCY, score_posting
from app.agents.scoring.prompts import FIT_SYSTEM
from app.agents.titles.agent import related_titles
from app.agents.triage.agent import MAX_CANDIDATES, shortlist
from app.config import Settings, get_settings
from app.constants import STRONG_FIT_SCORE
from app.db import service_db
from app.embeddings import embed_jobs
from app.sources import describe
from app.sources.base import Posting
from app.sources.filters import matches_rule
from app.telemetry import CallLog, ContextThreadPool, RecordingClient, prompt_version
from evals.results import save_result, usage_cost

DEFAULT_CUT = STRONG_FIT_SCORE
# Recent runs read to find the latest scored search.
RECENT_RUNS = 50
# Matches asked of the shortlist per pool slot, so the per-company cap can still fill the pool.
SHORTLIST_FACTOR = 2
# Title shortlisting calls at most; beyond them the newest matches are shortlisted.
MAX_TRIAGE_BATCHES = 10


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("Set ANTHROPIC_API_KEY to the key the scoring calls should use.")
        return
    db = service_db(settings)
    runs = db.select(
        "agent_runs",
        {
            "select": "user_id,input,created_at",
            "kind": "eq.search",
            "status": "eq.done",
            "user_id": "not.is.null",
            "order": "created_at.desc",
            "limit": str(RECENT_RUNS),
        },
    )
    run = next((r for r in runs if r["input"].get("score", True) and not r["input"].get("company")), None)
    if run is None:
        print("No finished scored search across all companies yet.")
        save_result(db, "ranking", {"skipped": "No finished scored search across all companies yet."})
        return
    rule = SearchRule.model_validate(run["input"])
    resumes = db.select("resumes", {"select": "text", "user_id": f"eq.{run['user_id']}", "is_primary": "eq.true"})
    if not resumes or not resumes[0]["text"]:
        print("That search's account has no primary resume text.")
        return
    resume = resumes[0]["text"]
    cut = rule.min_score or DEFAULT_CUT
    print(f"Search from {run['created_at'][:10]} · up to {rule.limit} jobs · cut {cut}")

    calls = CallLog()
    client = RecordingClient(anthropic.Anthropic(api_key=settings.anthropic_api_key), calls)
    titles = related_titles(client, settings.discovery_model, rule.keywords)
    keywords = [*rule.keywords, *titles]
    rows = db.select_all(
        "postings",
        {
            "select": "id,source,board,external_id,title,company,location,url,posted_at,workplace_type",
            "closed_at": "is.null",
            "source": "neq.hackernews",
        },
    )
    tracked_rows = db.select_all(
        "applications", {"select": "id,posting_id,posting:postings(company,title)", "user_id": f"eq.{run['user_id']}"}
    )
    tracked = {row["posting_id"] for row in tracked_rows}
    tracked_jobs = {job_key(row["posting"]["company"], row["posting"]["title"]) for row in tracked_rows}
    jobs = [Posting.model_validate({**row, "description": ""}) for row in rows if row["id"] not in tracked]
    matched = [p for p in jobs if matches_rule(p, rule, keywords) and job_key(p.company, p.title) not in tracked_jobs]
    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    fresh = [(saved_id(p), p) for p in one_per_job(one_per_title(matched))]
    pool_size = rule.limit * POOL_FACTOR
    print(f"{len(rows):,} open jobs, {len(fresh):,} match and aren't tracked; each method picks {pool_size}")
    if len(fresh) <= pool_size:
        print("Every match fits in one pool, so both methods would score the same jobs.")
        save_result(db, "ranking", {"skipped": "The latest search's matches fit in one pool."})
        return

    by_title = pick(by_title_fit(fresh, pool_size, client, settings, resume, shortlist), pool_size, MAX_PER_COMPANY)
    by_resume = pick(by_resume_fit(fresh, resume, db, embed_jobs), pool_size, MAX_PER_COMPANY)
    union = {posting_id: p for posting_id, p in [*by_title, *by_resume]}
    described = dict(with_descriptions(list(union.items()), db, describe))

    def score(item: tuple[str, Posting]) -> tuple[str, int]:
        return item[0], score_posting(client, settings.scoring_model, settings.scoring_effort, resume, item[1]).score

    first = score(next(iter(described.items())))
    with ThreadPoolExecutor(max_workers=SCORE_CONCURRENCY) as pool:
        results = [first, *pool.map(score, list(described.items())[1:])]
    scores = dict(results)

    methods: dict[str, Any] = {}
    for name, picked in (("Title shortlist", by_title), ("Resume similarity", by_resume)):
        values = [scores[posting_id] for posting_id, _ in picked if posting_id in scores]
        passing = sum(value >= cut for value in values)
        methods[name] = {"passing": passing, "scored": len(values), "mean": sum(values) / len(values)}
        print(f"\n{name}")
        print(f"  {passing} of {len(values)} reach {cut}; mean score {sum(values) / len(values):.1f}")
    both = {posting_id for posting_id, _ in by_title} & {posting_id for posting_id, _ in by_resume}
    print(f"\n{len(both)} jobs are in both pools")
    usage = calls.usage()
    cost = usage_cost(usage)
    print(f"Cost: ${cost:.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")
    save_result(
        db,
        "ranking",
        {"cut": cut, "pool": pool_size, "matches": len(fresh), "in_both": len(both), "methods": methods},
        cost,
        settings.scoring_model,
        prompt_version(FIT_SYSTEM, FitScore),
    )


def by_title_fit(
    fresh: list[tuple[str, Posting]],
    count: int,
    client: Any,
    settings: Settings,
    resume_text: str,
    triage: Callable[..., list[int]],
) -> list[tuple[str, Posting]]:
    """
    Reorders matches by how well their titles fit the resume, best first. Up to
    MAX_TRIAGE_BATCHES batches of MAX_CANDIDATES titles are shortlisted in
    parallel, then one more call ranks the batches' picks together. Each call
    asks for twice `count` so the per-company cap still leaves a full pool.
    """
    want = count * SHORTLIST_FACTOR

    def rank(candidates: list[tuple[str, Posting]]) -> list[tuple[str, Posting]]:
        picked = triage(client, settings.scoring_model, resume_text, [p for _, p in candidates], want)
        return [candidates[i] for i in picked]

    size = MAX_CANDIDATES
    batches = [fresh[i : i + size] for i in range(0, min(len(fresh), size * MAX_TRIAGE_BATCHES), size)]
    if len(batches) == 1:
        return rank(batches[0])
    with ContextThreadPool(max_workers=len(batches)) as pool:
        picks = list(pool.map(rank, batches))
    # Interleaved so each batch's best picks come first when the finalists are trimmed.
    finalists = [pick for rank_picks in zip_longest(*picks) for pick in rank_picks if pick is not None]
    return rank(finalists[:size])


if __name__ == "__main__":
    main()
