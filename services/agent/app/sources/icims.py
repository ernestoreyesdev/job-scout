import html
import re
from datetime import UTC, datetime

from app.sources.base import JobSource, Posting, distinct
from app.sources.text import country_name, inline_text, job_posting_description, workplace_from_location

HOST = "icims.com"
# Search pages read, and the jobs a page lists.
MAX_PAGES = 100
JOBS_PER_PAGE = 20
PAGE_CONCURRENCY = 8
CARD = re.compile(r'<li class="iCIMS_JobCardItem">(.*?)</li>', re.DOTALL)
LINK = re.compile(r'<a href="(https://[^"]+/jobs/(\d+)/[^"]*)"[^>]*class="iCIMS_Anchor"[^>]*>.*?<h3[^>]*>(.*?)</h3>', re.DOTALL)
LOCATION = re.compile(r"Job Locations?</span>\s*(?:</dt>\s*<dd[^>]*>)?\s*<span[^>]*>(.*?)</span>", re.DOTALL)
POSTED = re.compile(r'Posted Date</span>\s*<span title="([^"]+)"')
PAGES = re.compile(r"Page \d+ of ([\d,]+)")
# 'US-MA-Pittsfield', 'US-Remote', 'IN-Hyderabad'
CODED_PLACE = re.compile(r"^([A-Z]{2})-(?:([A-Z]{2})-)?(.+)$")


def _place(text: str | None) -> str | None:
    """'US-MA-Pittsfield' -> 'Pittsfield, MA, United States'; other text is kept as is."""
    if not text:
        return None
    match = CODED_PLACE.match(text)
    if not match:
        return text
    country, region, rest = match.groups()
    return ", ".join(part for part in (rest, region, country_name(country)) if part)


def _posted(title: str | None) -> datetime | None:
    """Cards give the posting time as '11/2/2026 12:00 PM' in a title attribute."""
    if not title:
        return None
    try:
        return datetime.strptime(title, "%m/%d/%Y %I:%M %p").replace(tzinfo=UTC)
    except ValueError:
        return None


class ICIMSSource(JobSource):
    """
    iCIMS career sites, read from their HTML search pages (no public API). Each
    page lists about JOBS_PER_PAGE job cards; pages after the first are read in parallel.
    Cards differ by company: location and posting date appear only when the
    company shows them. describe() reads a job page's JSON-LD. Each company's
    board is its subdomain, e.g. careers-gdms.icims.com.
    """

    name = "icims"
    label = "iCIMS"
    board_hosts = (HOST,)
    subdomain_boards = True
    reserved_paths = frozenset({"www", "careers", "community", "developer", "help", "info", "status"})
    max_jobs = MAX_PAGES * JOBS_PER_PAGE

    def fetch(self, board: str, company: str) -> list[Posting]:
        def page(number: int) -> str:
            return self._get_text(board, f"https://{board}.{HOST}/jobs/search", {"ss": "1", "in_iframe": "1", "pr": str(number)})

        first = page(0)
        total = PAGES.search(first)
        count = min(int(total[1].replace(",", "")), MAX_PAGES) if total else 1
        pages = [first, *self._pages(page, range(1, count), PAGE_CONCURRENCY)]

        cards = ((card, LINK.search(card)) for text in pages for card in CARD.findall(text))
        postings = []
        for card, link in distinct(cards, lambda pair: pair[1][2] if pair[1] else None):
            assert link is not None
            location = LOCATION.search(card)
            posted = POSTED.search(card)
            place = _place(inline_text(location[1])) if location else None
            postings.append(
                Posting(
                    source=self.name,
                    board=board,
                    external_id=link[2],
                    title=inline_text(link[3]),
                    company=company,
                    location=place,
                    url=html.unescape(link[1]).split("?")[0],
                    description="",
                    posted_at=_posted(posted[1]) if posted else None,
                    workplace_type=workplace_from_location(place),
                )
            )
        return postings

    def describe(self, posting: Posting) -> str:
        page = self._get_text(posting.board, posting.url, {"in_iframe": "1"})
        return job_posting_description(page)

    def board_candidates(self, company: str) -> list[str]:
        return [f"careers-{candidate}" for candidate in super().board_candidates(company)]

    def default_name(self, board: str) -> str:
        return super().default_name(re.sub(r"^[a-z]*careers-", "", board))

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOST}/jobs/search?ss=1"
