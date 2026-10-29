from datetime import UTC, date, datetime, time

from app.sources.base import JobSource, Posting
from app.sources.text import html_to_text, join_locations

API = "https://apply.workable.com/api/v1/widget/accounts"


def _posted(day: str | None) -> datetime | None:
    return datetime.combine(date.fromisoformat(day), time(), UTC) if day else None


class WorkableSource(JobSource):
    """
    Workable job widget API: one request with details=true returns every job
    with its description. It only says whether a job is remote, so other jobs
    have no workplace type.
    """

    name = "workable"
    label = "Workable"
    board_hosts = ("apply.workable.com",)
    reserved_paths = frozenset({"j", "api"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"{API}/{board}", {"details": "true"})
        return [
            Posting(
                source="workable",
                board=board,
                external_id=job["shortcode"],
                title=job["title"],
                company=data.get("name") or company,
                location=join_locations(
                    *(
                        ", ".join(part for part in (place.get("city"), place.get("region"), place.get("country")) if part)
                        for place in job.get("locations") or []
                    )
                ),
                url=job["url"],
                description=html_to_text(job.get("description") or ""),
                posted_at=_posted(job.get("published_on")),
                workplace_type="remote" if job.get("telecommuting") else None,
            )
            for job in data["jobs"]
        ]
