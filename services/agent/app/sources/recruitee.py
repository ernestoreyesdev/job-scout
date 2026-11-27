from datetime import UTC, datetime

from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import html_to_text

HOST = "recruitee.com"


def _workplace(job: dict) -> WorkplaceType | None:
    if job.get("remote"):
        return "remote"
    if job.get("hybrid"):
        return "hybrid"
    return "onsite" if job.get("on_site") else None


def _posted(stamp: str | None) -> datetime | None:
    """Recruitee timestamps look like '2026-10-28 13:21:58 UTC'."""
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=UTC) if stamp else None


class RecruiteeSource(JobSource):
    """
    Recruitee careers API: one request returns every published offer with its
    description and requirements. Each company's board is the subdomain
    {board}.recruitee.com.
    """

    name = "recruitee"
    label = "Recruitee"
    board_hosts = (HOST,)
    subdomain_boards = True
    reserved_paths = frozenset({"www", "api", "app", "careers", "blog", "support"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"https://{board}.{HOST}/api/offers/")
        return [
            Posting(
                source=self.name,
                board=board,
                external_id=str(job["id"]),
                title=job["title"],
                company=job.get("company_name") or company,
                location=job.get("location") or None,
                url=job["careers_url"],
                description="\n\n".join(
                    html_to_text(job.get(field) or "") for field in ("description", "requirements") if job.get(field)
                ),
                posted_at=_posted(job.get("published_at")),
                workplace_type=_workplace(job),
            )
            for job in data["offers"]
            if job.get("status", "published") == "published"
        ]
