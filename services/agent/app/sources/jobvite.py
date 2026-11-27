import re

from app.sources.base import JobSource, Posting, distinct
from app.sources.text import inline_text, job_posting_description, workplace_from_location

HOST = "jobs.jobvite.com"
ROW = re.compile(
    r'<td class="jv-job-list-name">\s*<a href="/[^/"]+/job/([^"/?]+)"[^>]*>(.*?)</a>\s*</td>\s*'
    r'<td class="jv-job-list-location">(.*?)</td>',
    re.DOTALL,
)


class JobviteSource(JobSource):
    """
    Jobvite career sites, read from their HTML job list (no public API). One
    page lists every job, grouped by department; jobs in several places say
    only '2 Locations'. describe() reads a job page's JSON-LD. An unknown
    company redirects to Jobvite's support site.
    """

    name = "jobvite"
    label = "Jobvite"
    board_hosts = (HOST,)
    reserved_paths = frozenset({"api", "search", "support"})
    not_found_statuses = frozenset({301, 302, 303, 404})

    def fetch(self, board: str, company: str) -> list[Posting]:
        page = self._get_text(board, f"https://{HOST}/{board}/jobs")
        postings = []
        for job_id, title, location in distinct(ROW.findall(page), lambda row: row[0]):
            place = inline_text(location) or None
            postings.append(
                Posting(
                    source=self.name,
                    board=board,
                    external_id=job_id,
                    title=inline_text(title),
                    company=company,
                    location=place,
                    url=f"https://{HOST}/{board}/job/{job_id}",
                    description="",
                    posted_at=None,
                    workplace_type=workplace_from_location(place),
                )
            )
        return postings

    def describe(self, posting: Posting) -> str:
        page = self._get_text(posting.board, posting.url)
        return job_posting_description(page)

    def careers_url(self, board: str) -> str:
        return f"https://{HOST}/{board}/jobs"
