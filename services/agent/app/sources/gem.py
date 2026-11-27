from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import html_to_text, join_locations

API = "https://api.gem.com/job_board/v0"
WORKPLACES: dict[str, WorkplaceType] = {"remote": "remote", "hybrid": "hybrid", "in_office": "onsite"}


class GemSource(JobSource):
    """Gem job board API: one request returns every job with its description."""

    name = "gem"
    label = "Gem"
    board_hosts = ("jobs.gem.com",)

    def fetch(self, board: str, company: str) -> list[Posting]:
        jobs = self._get_json(board, f"{API}/{board}/job_posts/")
        return [
            Posting(
                source=self.name,
                board=board,
                external_id=job["id"],
                title=job["title"],
                company=company,
                location=join_locations(
                    *(office.get("location", {}).get("name") for office in job.get("offices") or []),
                    (job.get("location") or {}).get("name"),
                ),
                url=job["absolute_url"],
                description=html_to_text(job.get("content") or ""),
                posted_at=job.get("first_published_at") or job.get("created_at"),
                workplace_type=WORKPLACES.get(job.get("location_type") or ""),
            )
            for job in jobs
        ]
