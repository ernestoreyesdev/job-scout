import httpx

from app.sources.base import BoardNotFound, Posting, WorkplaceType, join_locations

API = "https://api.ashbyhq.com/posting-api/job-board"
WORKPLACE: dict[str, WorkplaceType] = {"OnSite": "onsite", "Hybrid": "hybrid", "Remote": "remote"}


class AshbySource:
    """Public Ashby job board API; no credentials needed."""

    name = "ashby"

    def __init__(self, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30)

    def fetch(self, board: str, company: str) -> list[Posting]:
        res = self._http.get(f"{API}/{board}")
        if res.status_code == 404:
            raise BoardNotFound(f"Ashby board '{board}' does not exist.")
        res.raise_for_status()

        return [
            Posting(
                source="ashby",
                board=board,
                external_id=job["id"],
                title=job["title"],
                company=company,
                location=join_locations(
                    job.get("location"), *(extra.get("location") for extra in job.get("secondaryLocations") or [])
                ),
                url=job["jobUrl"],
                description=job.get("descriptionPlain") or "",
                posted_at=job.get("publishedAt"),
                workplace_type=WORKPLACE.get(job.get("workplaceType") or ""),
            )
            for job in res.json()["jobs"]
            if job.get("isListed", True)
        ]
