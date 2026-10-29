from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import join_locations, with_country

API = "https://api.ashbyhq.com/posting-api/job-board"
WORKPLACE: dict[str, WorkplaceType] = {"OnSite": "onsite", "Hybrid": "hybrid", "Remote": "remote"}


def _country(location: dict) -> str | None:
    return ((location.get("address") or {}).get("postalAddress") or {}).get("addressCountry")


class AshbySource(JobSource):
    """Ashby job board API: one request returns every listed job with its description."""

    name = "ashby"
    label = "Ashby"
    board_hosts = ("jobs.ashbyhq.com",)

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"{API}/{board}")
        return [
            Posting(
                source="ashby",
                board=board,
                external_id=job["id"],
                title=job["title"],
                company=company,
                location=join_locations(
                    with_country(job.get("location"), _country(job)),
                    *(with_country(extra.get("location"), _country(extra)) for extra in job.get("secondaryLocations") or []),
                ),
                url=job["jobUrl"],
                description=job.get("descriptionPlain") or "",
                posted_at=job.get("publishedAt"),
                workplace_type=WORKPLACE.get(job.get("workplaceType") or ""),
            )
            for job in data["jobs"]
            if job.get("isListed", True)
        ]
