
from app.sources.base import JobSource, Posting
from app.sources.text import html_to_text, join_locations, workplace_from_location

HOST = "bamboohr.com"


def _location(job: dict) -> str | None:
    """City, state and country from the job's address and its ATS location, each named once."""
    place = job.get("location") or {}
    ats = job.get("atsLocation") or {}
    return join_locations(
        place.get("city"),
        place.get("state"),
        ats.get("city"),
        ats.get("state") or ats.get("province"),
        ats.get("country"),
        separator=", ",
    )


class BambooHRSource(JobSource):
    """
    BambooHR careers pages, through the JSON endpoints the pages themselves
    call (not a published API). The list has no descriptions or dates, so
    describe() fetches one job's details. Each company's board is a subdomain,
    {board}.bamboohr.com, and an unknown one redirects to BambooHR's homepage.
    """

    name = "bamboohr"
    label = "BambooHR"
    board_hosts = (HOST,)
    subdomain_boards = True
    reserved_paths = frozenset({"www", "api", "app", "help", "partners", "marketplace", "status"})
    not_found_statuses = frozenset({301, 302, 404})

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"https://{board}.{HOST}/careers/list")
        return [
            Posting(
                source="bamboohr",
                board=board,
                external_id=str(job["id"]),
                title=job["jobOpeningName"].strip(),
                company=company,
                location=_location(job),
                url=f"https://{board}.{HOST}/careers/{job['id']}",
                description="",
                posted_at=None,
                workplace_type="remote" if job.get("isRemote") else workplace_from_location(_location(job)),
            )
            for job in data.get("result") or []
        ]

    def describe(self, posting: Posting) -> str:
        details = self._get_json(posting.board, f"https://{posting.board}.{HOST}/careers/{posting.external_id}/detail")
        opening = (details.get("result") or {}).get("jobOpening") or {}
        return html_to_text(opening.get("description") or "")

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOST}/careers"
