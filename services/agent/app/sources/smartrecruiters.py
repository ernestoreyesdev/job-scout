from app.sources.base import BoardNotFound, JobSource, Posting, WorkplaceType
from app.sources.text import country_name, html_to_text

API = "https://api.smartrecruiters.com/v1/companies"
JOB_PAGE = "https://jobs.smartrecruiters.com"
PAGE_SIZE = 100


def _workplace(location: dict) -> WorkplaceType:
    if location.get("remote"):
        return "remote"
    return "hybrid" if location.get("hybrid") else "onsite"


def _location(location: dict) -> str | None:
    parts = [location.get("city"), location.get("region"), country_name(location.get("country"))]
    return ", ".join(part for part in parts if part) or None


class SmartRecruitersSource(JobSource):
    """
    SmartRecruiters posting API. Lists come in pages of 100 without descriptions,
    so describe() fetches one posting's details. An unknown company returns an
    empty list rather than 404, so no postings counts as no board.
    """

    name = "smartrecruiters"
    label = "SmartRecruiters"
    board_hosts = ("jobs.smartrecruiters.com",)

    def fetch(self, board: str, company: str) -> list[Posting]:
        jobs: list[dict] = []
        while True:
            page = self._get_json(board, f"{API}/{board}/postings", {"limit": PAGE_SIZE, "offset": len(jobs)})
            jobs += page["content"]
            if not page["content"] or len(jobs) >= page["totalFound"]:
                break
        if not jobs:
            raise BoardNotFound(f"{self.label} board '{board}' does not exist.")

        return [
            Posting(
                source="smartrecruiters",
                board=board,
                external_id=job["id"],
                title=job["name"],
                company=(job.get("company") or {}).get("name") or company,
                location=_location(job.get("location") or {}),
                url=f"{JOB_PAGE}/{board}/{job['id']}",
                description="",
                posted_at=job.get("releasedDate"),
                workplace_type=_workplace(job.get("location") or {}),
            )
            for job in jobs
        ]

    def describe(self, posting: Posting) -> str:
        details = self._get_json(posting.board, f"{API}/{posting.board}/postings/{posting.external_id}")
        sections = ((details.get("jobAd") or {}).get("sections") or {}).values()
        return "\n\n".join(
            f"{section.get('title', '')}\n{html_to_text(section.get('text') or '')}".strip()
            for section in sections
            if section.get("text")
        )
