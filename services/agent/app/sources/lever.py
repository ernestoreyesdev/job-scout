from datetime import UTC, datetime

from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import country_name, html_to_text, join_locations, with_country

API = "https://api.lever.co/v0/postings"
WORKPLACE: dict[str, WorkplaceType] = {"onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}


def _description(job: dict) -> str:
    """Intro, then each titled list (responsibilities, requirements), then the closing text."""
    parts = [job.get("descriptionPlain") or ""]
    for section in job.get("lists") or []:
        parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content') or '')}")
    parts.append(job.get("additionalPlain") or "")
    return "\n\n".join(part.strip() for part in parts if part.strip())


class LeverSource(JobSource):
    """Lever postings API: one request returns every job with its description."""

    name = "lever"
    label = "Lever"
    board_hosts = ("jobs.lever.co",)

    def fetch(self, board: str, company: str) -> list[Posting]:
        jobs = self._get_json(board, f"{API}/{board}", {"mode": "json"})
        return [
            Posting(
                source="lever",
                board=board,
                external_id=job["id"],
                title=job["text"],
                company=company,
                location=join_locations(
                    with_country((job.get("categories") or {}).get("location"), country_name(job.get("country"))),
                    *(job.get("categories") or {}).get("allLocations") or [],
                ),
                url=job["hostedUrl"],
                description=_description(job),
                posted_at=datetime.fromtimestamp(job["createdAt"] / 1000, UTC) if job.get("createdAt") else None,
                workplace_type=WORKPLACE.get(job.get("workplaceType") or ""),
            )
            for job in jobs
        ]
