import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.sources.base import BOARD_SLUG, JobSource, Posting
from app.sources.text import country_name, html_to_text, job_posting_ld, workplace_from_location

HOST = "icims.com"
# Search pages read; boards list about 20 jobs per page.
MAX_PAGES = 100
PAGE_CONCURRENCY = 8
CARD = re.compile(r'<li class="iCIMS_JobCardItem">(.*?)</li>', re.S)
LINK = re.compile(r'<a href="(https://[^"]+/jobs/(\d+)/[^"]*)"[^>]*class="iCIMS_Anchor"[^>]*>.*?<h3[^>]*>(.*?)</h3>', re.S)
LOCATION = re.compile(r"Job Locations?</span>\s*(?:</dt>\s*<dd[^>]*>)?\s*<span[^>]*>(.*?)</span>", re.S)
POSTED = re.compile(r'Posted Date</span>\s*<span title="([^"]+)"')
PAGES = re.compile(r"Page \d+ of ([\d,]+)")
# 'US-MA-Pittsfield', 'US-Remote', 'IN-Hyderabad'
CODED_PLACE = re.compile(r"^([A-Z]{2})-(?:([A-Z]{2})-)?(.+)$")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


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
    page lists about 20 job cards; pages after the first are read in parallel.
    Cards differ by company: location and posting date appear only when the
    company shows them. describe() reads a job page's JSON-LD. Each company's
    board is its subdomain, e.g. careers-gdms.icims.com.
    """

    name = "icims"
    label = "iCIMS"
    board_hosts = (HOST,)
    reserved_paths = frozenset({"www", "careers", "community", "developer", "help", "info", "status"})
    max_jobs = MAX_PAGES * 20

    def fetch(self, board: str, company: str) -> list[Posting]:
        def page(number: int) -> str:
            return self._get_text(board, f"https://{board}.{HOST}/jobs/search", {"ss": "1", "in_iframe": "1", "pr": str(number)})

        first = page(0)
        total = PAGES.search(first)
        count = min(int(total[1].replace(",", "")), MAX_PAGES) if total else 1
        with ThreadPoolExecutor(max_workers=PAGE_CONCURRENCY) as pool:
            pages = [first, *pool.map(page, range(1, count))]

        seen: set[str] = set()
        postings = []
        for card in (card for text in pages for card in CARD.findall(text)):
            link = LINK.search(card)
            if not link or link[2] in seen:
                continue
            seen.add(link[2])
            location = LOCATION.search(card)
            posted = POSTED.search(card)
            place = _place(_text(location[1])) if location else None
            postings.append(
                Posting(
                    source="icims",
                    board=board,
                    external_id=link[2],
                    title=_text(link[3]),
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
        return html_to_text(job_posting_ld(page).get("description") or "")

    def board_candidates(self, company: str) -> list[str]:
        return [f"careers-{candidate}" for candidate in super().board_candidates(company)]

    def default_name(self, board: str) -> str:
        return super().default_name(re.sub(r"^[a-z]*careers-", "", board))

    def board_from_url(self, url: str) -> str | None:
        host = (urlparse(url).hostname or "").lower()
        if not host.endswith(f".{HOST}"):
            return None
        board = host.removesuffix(f".{HOST}")
        return board if BOARD_SLUG.match(board) and board not in self.reserved_paths else None

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOST}/jobs/search?ss=1"
