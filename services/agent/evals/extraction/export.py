"""
Writes the eval postings, as the scoring call sees them, to postings.local.json
(gitignored): `uv run python -m evals.extraction.export`. With --pick it first
chooses a new set of postings from the local database and saves their keys to
selection.json.
"""

import json
import sys
from pathlib import Path

from app.agents.scoring.prompts import trim_description
from app.config import get_settings
from app.db import service_db
from app.sources.base import Posting

HERE = Path(__file__).parent
SELECTION = HERE / "selection.json"
INPUTS = HERE / "postings.local.json"
# Postings per source, then every posting that mentions a clearance or visa sponsorship on top.
PER_SOURCE = {"greenhouse": 10, "lever": 8, "ashby": 5, "workable": 3, "hackernews": 8}
TOPICS = {"clearance": 6, "sponsor": 6}


def pick(db) -> list[dict[str, str]]:
    chosen: dict[tuple[str, str], None] = {}
    for source, count in PER_SOURCE.items():
        rows = db.select(
            "postings",
            {"select": "source,external_id", "source": f"eq.{source}", "description": "neq.", "order": "external_id", "limit": "500"},
        )
        step = max(1, len(rows) // count)
        for row in rows[::step][:count]:
            chosen[(row["source"], row["external_id"])] = None
    for word, count in TOPICS.items():
        rows = db.select(
            "postings",
            {"select": "source,external_id", "description": f"ilike.*{word}*", "order": "external_id", "limit": str(count * 3)},
        )
        for row in rows[:count]:
            chosen[(row["source"], row["external_id"])] = None
    return [{"source": source, "external_id": external_id} for source, external_id in chosen]


def main() -> None:
    db = service_db(get_settings())
    if "--pick" in sys.argv:
        SELECTION.write_text(json.dumps(pick(db), indent=2) + "\n")
    selection = json.loads(SELECTION.read_text())
    inputs = []
    for key in selection:
        [row] = db.select("postings", {"select": "*", "source": f"eq.{key['source']}", "external_id": f"eq.{key['external_id']}"})
        posting = Posting.model_validate(row)
        inputs.append({**key, "title": posting.title, "company": posting.company, "location": posting.location, "text": trim_description(posting.description)})
    INPUTS.write_text(json.dumps(inputs, indent=2) + "\n")
    print(f"Wrote {len(inputs)} postings to {INPUTS.name}")


if __name__ == "__main__":
    main()
