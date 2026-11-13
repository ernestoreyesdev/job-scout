"""
Embeds every open job that has no embedding yet, newest first, a batch at a
time: `uv run python -m scripts.backfill_embeddings`. The daily refresh does
the same after saving jobs; this runs it on its own. Point
it at the hosted project by setting SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
for that project. Safe to stop and rerun.
"""

import time

from app.agents.orchestrator import embed_missing
from app.config import get_settings
from app.db import service_db
from app.embeddings import embed_jobs

BATCH = 500


def main() -> None:
    service = service_db(get_settings())
    started = time.monotonic()
    total = 0
    while count := embed_missing(service, embed_jobs, BATCH):
        total += count
        print(f"{total:,} jobs embedded, {time.monotonic() - started:.0f} s")
    print(f"Done: {total:,} jobs embedded in {time.monotonic() - started:.0f} s")


if __name__ == "__main__":
    main()
