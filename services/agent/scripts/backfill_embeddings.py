"""
Embeds every open job that has no embedding yet, newest first, a batch at a
time: `uv run python -m scripts.backfill_embeddings`. Like the daily refresh,
it first fetches every directory board except staffing agencies and embeds
each job from the description its board lists, or the saved one; a job with
neither is embedded from its title, company and location. Point it at the
hosted project by setting SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for that
project. Safe to stop and rerun.
"""

import time

from app.agents.orchestrator import SKIPPED_KINDS, Board, embed_missing, fetch_boards
from app.config import get_settings
from app.db import service_db
from app.embeddings import embed_jobs
from app.sources import fetch_live

BATCH = 500


def main() -> None:
    service = service_db(get_settings())
    started = time.monotonic()
    directory = service.select("companies", {"select": "source,board,name,found_by,kind"})
    boards = [
        Board(c["source"], c["board"], c["name"], c["found_by"]) for c in directory if c["kind"] not in SKIPPED_KINDS
    ]
    fetched, _, unreachable, _ = fetch_boards(boards, fetch_live, lambda _: None)
    descriptions = {(p.source, p.external_id): p.description for postings in fetched.values() for p in postings}
    print(f"Fetched {len(fetched):,} boards, {len(unreachable):,} unreachable, {time.monotonic() - started:.0f} s")
    total = 0
    while count := embed_missing(service, embed_jobs, BATCH, descriptions):
        total += count
        print(f"{total:,} jobs embedded, {time.monotonic() - started:.0f} s")
    print(f"Done: {total:,} jobs embedded in {time.monotonic() - started:.0f} s")


if __name__ == "__main__":
    main()
