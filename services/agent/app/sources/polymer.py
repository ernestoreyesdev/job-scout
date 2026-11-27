from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import html_to_text

API = "https://api.polymer.co/v1/hire/organizations"
WORKPLACES: dict[str, WorkplaceType] = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite", "onsite": "onsite"}


class PolymerSource(JobSource):
    """
    Polymer job board API. Lists come in pages without descriptions, so
    describe() fetches one job's details. An unknown board answers 422.
    """

    name = "polymer"
    label = "Polymer"
    board_hosts = ("jobs.polymer.co",)
    not_found_statuses = frozenset({404, 422})

    def fetch(self, board: str, company: str) -> list[Posting]:
        jobs: list[dict] = []
        page = 1
        while True:
            data = self._get_json(board, f"{API}/{board}/jobs", {"page": page})
            jobs += data["items"]
            if data["meta"].get("is_last", True) or not data["items"]:
                break
            page += 1
        return [
            Posting(
                source=self.name,
                board=board,
                external_id=str(job["id"]),
                title=job["title"],
                company=job.get("organization_name") or company,
                location=job.get("display_location") or None,
                url=job["job_post_url"],
                description="",
                posted_at=job.get("published_at") or job.get("created_at"),
                workplace_type=WORKPLACES.get((job.get("remoteness_pretty") or "").lower()),
            )
            for job in jobs
        ]

    def describe(self, posting: Posting) -> str:
        job = self._get_json(posting.board, f"{API}/{posting.board}/jobs/{posting.external_id}")
        return html_to_text(job.get("description") or "")
