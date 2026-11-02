import html
import re

from app.sources.base import JobSource, Posting
from app.sources.text import html_to_text, job_posting_ld, workplace_from_location

HOST = "jobs.jobvite.com"
ROW = re.compile(
    r'<td class="jv-job-list-name">\s*<a href="/[^/"]+/job/([^"/?]+)"[^>]*>(.*?)</a>\s*</td>\s*'
    r'<td class="jv-job-list-location">(.*?)</td>',
    re.S,
)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


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
        seen: set[str] = set()
        postings = []
        for job_id, title, location in ROW.findall(page):
            if job_id in seen:
                continue
            seen.add(job_id)
            place = _text(location) or None
            postings.append(
                Posting(
                    source="jobvite",
                    board=board,
                    external_id=job_id,
                    title=_text(title),
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
        return html_to_text(job_posting_ld(page).get("description") or "")

    def careers_url(self, board: str) -> str:
        return f"https://{HOST}/{board}/jobs"
