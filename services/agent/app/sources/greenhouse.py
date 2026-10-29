from app.sources.base import JobSource, Posting
from app.sources.text import html_to_text, workplace_from_location

API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(JobSource):
    """Greenhouse job board API: one request returns every job with its description."""

    name = "greenhouse"
    label = "Greenhouse"
    board_hosts = ("boards.greenhouse.io", "job-boards.greenhouse.io")
    reserved_paths = frozenset({"embed", "job-openings", "jobs"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"{API}/{board}/jobs", {"content": "true"})
        return [
            Posting(
                source="greenhouse",
                board=board,
                external_id=str(job["id"]),
                title=job["title"],
                company=job.get("company_name") or company,
                location=(job.get("location") or {}).get("name"),
                url=job["absolute_url"],
                description=html_to_text(job.get("content") or ""),
                posted_at=job.get("first_published") or job.get("updated_at"),
                workplace_type=workplace_from_location((job.get("location") or {}).get("name")),
            )
            for job in data["jobs"]
        ]

    def careers_url(self, board: str) -> str:
        return f"https://job-boards.greenhouse.io/{board}"
