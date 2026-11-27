import re
from urllib.parse import urlparse

from app.sources.base import BOARD_SLUG, JobSource, Posting
from app.sources.text import html_to_text, workplace_from_location

HOST = "ats.rippling.com"
API = "https://api.rippling.com/platform/api/ats/v1/board"
LOCALE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


class RipplingSource(JobSource):
    """
    Rippling ATS job board API. Lists come without descriptions or dates, so
    describe() fetches one job's details. Job pages are ats.rippling.com/{board}/jobs/{id},
    sometimes with a locale segment ('/en-ca/') before the board.
    """

    name = "rippling"
    label = "Rippling"
    board_hosts = (HOST,)

    def fetch(self, board: str, company: str) -> list[Posting]:
        jobs = self._get_json(board, f"{API}/{board}/jobs")
        return [
            Posting(
                source=self.name,
                board=board,
                external_id=job["uuid"],
                title=job["name"],
                company=company,
                location=(job.get("workLocation") or {}).get("label"),
                url=job["url"],
                description="",
                posted_at=None,
                workplace_type=workplace_from_location((job.get("workLocation") or {}).get("label")),
            )
            for job in jobs
        ]

    def describe(self, posting: Posting) -> str:
        job = self._get_json(posting.board, f"{API}/{posting.board}/jobs/{posting.external_id}")
        sections = job.get("description") or {}
        return "\n\n".join(html_to_text(sections[part]) for part in ("company", "role") if sections.get(part))

    def board_from_url(self, url: str) -> str | None:
        """https://ats.rippling.com/en-ca/flyover-las-vegas/jobs/... -> flyover-las-vegas"""
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() != HOST:
            return None
        segments = [s for s in parsed.path.lower().split("/") if s]
        if segments and LOCALE.match(segments[0]) and len(segments) > 1:
            segments = segments[1:]
        board = segments[0] if segments else ""
        return board if BOARD_SLUG.match(board) else None

    def careers_url(self, board: str) -> str:
        return f"https://{HOST}/{board}/jobs"
