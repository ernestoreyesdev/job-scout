"""
Compares how searches pick which jobs to score: `uv run python -m
evals.ranking.run`. Takes the most recent scored search, matches its rule
against the saved open jobs the way a search does, and builds the scoring pool
twice: once with the Claude title shortlist and once by resume similarity.
Every job in either pool is scored without labeled examples, and each method's
pool is reported by how many reach the min score (70 when the search had none).
A run costs about one shortlist call per 300 matches plus up to two scoring
calls per job in the pool. Point it at the hosted project by setting
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and ANTHROPIC_API_KEY.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import anthropic

from app.agents.orchestrator import (
    MAX_PER_COMPANY,
    POOL_FACTOR,
    by_resume_fit,
    by_title_fit,
    one_per_job,
    one_per_title,
    pick,
    with_descriptions,
)
from app.agents.schemas import SearchRule, Usage
from app.agents.scoring.agent import score_posting
from app.agents.titles.agent import related_titles
from app.agents.triage.agent import shortlist
from app.config import get_settings
from app.db import service_db
from app.embeddings import embed_jobs
from app.main import select_all
from app.sources import describe
from app.sources.base import Posting
from app.sources.filters import matches_exclusions, matches_keywords, matches_location, matches_workplace, posted_within

DEFAULT_CUT = 70
# Haiku 5.5 prices per million tokens: input, output, cache read, cache write.
PRICES = (0.10, 0.50, 0.01, 0.125)


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("Set ANTHROPIC_API_KEY to the key the scoring calls should use.")
        return
    db = service_db(settings)
    runs = db.select(
        "agent_runs",
        {"select": "user_id,input,created_at", "kind": "eq.search", "status": "eq.done", "order": "created_at.desc", "limit": "50"},
    )
    run = next((r for r in runs if r["input"].get("score", True) and not r["input"].get("company")), None)
    if run is None:
        print("No finished scored search across all companies yet.")
        return
    rule = SearchRule.model_validate(run["input"])
    resumes = db.select("resumes", {"select": "text", "user_id": f"eq.{run['user_id']}", "is_primary": "eq.true"})
    if not resumes or not resumes[0]["text"]:
        print("That search's account has no primary resume text.")
        return
    resume = resumes[0]["text"]
    cut = rule.min_score or DEFAULT_CUT
    print(f"Search from {run['created_at'][:10]}: {', '.join(rule.keywords)} · up to {rule.limit} jobs · cut {cut}")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    usage = Usage()
    titles = related_titles(client, settings.discovery_model, rule.keywords, usage)
    keywords = [*rule.keywords, *titles]
    rows = select_all(
        db,
        "postings",
        {
            "select": "id,source,board,external_id,title,company,location,url,posted_at,workplace_type",
            "closed_at": "is.null",
            "source": "neq.hackernews",
            "order": "id",
        },
    )
    tracked = {row["posting_id"] for row in select_all(db, "applications", {"select": "posting_id", "user_id": f"eq.{run['user_id']}", "order": "id"})}
    jobs = {row["id"]: Posting.model_validate({**row, "description": ""}) for row in rows if row["id"] not in tracked}
    matched = [
        p
        for p in jobs.values()
        if matches_keywords(p, keywords)
        and matches_exclusions(p, rule.exclude)
        and matches_workplace(p, rule.workplace_types)
        and matches_location(p, rule.location)
        and posted_within(p, rule.posted_within_days)
    ]
    matched.sort(key=lambda p: p.posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    ids = {(p.source, p.external_id): posting_id for posting_id, p in jobs.items()}
    fresh = [(ids[(p.source, p.external_id)], p) for p in one_per_job(one_per_title(matched))]
    pool_size = rule.limit * POOL_FACTOR
    print(f"{len(rows):,} open jobs, {len(fresh):,} match and aren't tracked; each method picks {pool_size}")
    if len(fresh) <= pool_size:
        print("Every match fits in one pool, so both methods would score the same jobs.")
        return

    by_title = pick(by_title_fit(fresh, pool_size, client, settings, resume, usage, shortlist), pool_size, MAX_PER_COMPANY)
    by_resume = pick(by_resume_fit(fresh, resume, db, embed_jobs), pool_size, MAX_PER_COMPANY)
    union = {posting_id: p for posting_id, p in [*by_title, *by_resume]}
    described = dict(with_descriptions(list(union.items()), db, describe))

    def score(item: tuple[str, Posting]) -> tuple[str, int, object]:
        fit, call_usage = score_posting(client, settings.scoring_model, settings.scoring_effort, resume, item[1])
        return item[0], fit.score, call_usage

    first = score(next(iter(described.items())))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [first, *pool.map(score, list(described.items())[1:])]
    scores = {posting_id: value for posting_id, value, _ in results}
    for *_, call_usage in results:
        usage.add(call_usage)

    for name, picked in (("Title shortlist", by_title), ("Resume similarity", by_resume)):
        values = [scores[posting_id] for posting_id, _ in picked if posting_id in scores]
        passing = sum(value >= cut for value in values)
        print(f"\n{name}")
        print(f"  {passing} of {len(values)} reach {cut}; mean score {sum(values) / len(values):.1f}")
        for posting_id, p in sorted(picked, key=lambda job: -scores.get(job[0], -1))[:5]:
            print(f"  {scores.get(posting_id, '–'):>3}  {p.title} · {p.company}")
    both = {posting_id for posting_id, _ in by_title} & {posting_id for posting_id, _ in by_resume}
    print(f"\n{len(both)} jobs are in both pools")
    cost = sum(
        n * price / 1_000_000
        for n, price in zip(
            (usage.input_tokens, usage.output_tokens, usage.cache_read_input_tokens, usage.cache_creation_input_tokens),
            PRICES,
        )
    )
    print(f"Cost: ${cost:.3f} ({usage.input_tokens:,} input, {usage.output_tokens:,} output tokens)")


if __name__ == "__main__":
    main()
