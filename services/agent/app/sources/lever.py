from datetime import UTC, datetime

import httpx

from app.sources.base import BoardNotFound, Posting, WorkplaceType, join_locations
from app.sources.greenhouse import html_to_text

API = "https://api.lever.co/v0/postings"
WORKPLACE: dict[str, WorkplaceType] = {"onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}


def _description(job: dict) -> str:
    """Intro, then each titled list (responsibilities, requirements), then the closing text."""
    parts = [job.get("descriptionPlain") or ""]
    for section in job.get("lists") or []:
        parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content') or '')}")
    parts.append(job.get("additionalPlain") or "")
    return "\n\n".join(part.strip() for part in parts if part.strip())


class LeverSource:
    """Public Lever postings API; no credentials needed."""

    name = "lever"

    def __init__(self, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30)

    def fetch(self, board: str, company: str) -> list[Posting]:
        res = self._http.get(f"{API}/{board}", params={"mode": "json"})
        if res.status_code == 404:
            raise BoardNotFound(f"Lever board '{board}' does not exist.")
        res.raise_for_status()

        return [
            Posting(
                source="lever",
                board=board,
                external_id=job["id"],
                title=job["text"],
                company=company,
                location=join_locations(
                    (job.get("categories") or {}).get("location"), *(job.get("categories") or {}).get("allLocations") or []
                ),
                url=job["hostedUrl"],
                description=_description(job),
                posted_at=datetime.fromtimestamp(job["createdAt"] / 1000, UTC) if job.get("createdAt") else None,
                workplace_type=WORKPLACE.get(job.get("workplaceType") or ""),
            )
            for job in res.json()
        ]
