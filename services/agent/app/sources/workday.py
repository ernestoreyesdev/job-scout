import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from app.sources.base import BoardNotFound, JobSource, Posting
from app.sources.text import html_to_text, workplace_from_location

HOST = "myworkdayjobs.com"
PAGE_SIZE = 20
# Workday serves at most this many jobs per query; later offsets repeat the first page.
MAX_JOBS = 2000
PAGE_CONCURRENCY = 8
BOARD = re.compile(r"^(?P<tenant>[a-z0-9-]+)\.(?P<server>wd\d+)/(?P<site>[a-z0-9_-]+)$")
LOCALE = re.compile(r"^[a-z]{2}-[a-z]{2}$")
DAYS_AGO = re.compile(r"(\d+)\+? Days? Ago")
SEVERAL_LOCATIONS = re.compile(r"(\d+) Locations")


def _parts(board: str) -> tuple[str, str, str]:
    match = BOARD.match(board)
    if not match:
        raise BoardNotFound(f"Workday board '{board}' isn't in tenant.wdN/site form.")
    return match["tenant"], match["server"], match["site"]


def _location(job: dict) -> str | None:
    """
    Lists say '6 Locations' for jobs in several places; the job's path still
    names its main one (/job/US-CA-Santa-Clara/...), so that is used instead.
    """
    text = job.get("locationsText") or None
    several = SEVERAL_LOCATIONS.fullmatch(text or "")
    segments = (job.get("externalPath") or "").split("/")
    if not several or len(segments) < 3 or segments[1] != "job":
        return text
    return f"{segments[2].replace('-', ' ')} and {int(several[1]) - 1} more"


def _posted(text: str | None, today: datetime) -> datetime | None:
    """Workday lists say 'Posted Today', 'Posted Yesterday' or 'Posted 3 Days Ago'; '30+ Days Ago' counts as 30."""
    if not text:
        return None
    if "Today" in text:
        return today
    if "Yesterday" in text:
        return today - timedelta(days=1)
    match = DAYS_AGO.search(text)
    return today - timedelta(days=int(match[1])) if match else None


class WorkdaySource(JobSource):
    """
    Workday career sites, through the JSON endpoint their own pages call (not a
    published API). A board is 'tenant.wdN/site', e.g. 'nvidia.wd5/nvidiaexternalcareersite',
    since a company is identified by all three. Lists come 20 jobs per request
    without descriptions or exact dates, so pages are read in parallel and
    describe() fetches one job's details. Boards can't be guessed from a
    company name; they come from discovery.
    """

    name = "workday"
    label = "Workday"
    board_hosts = (HOST,)
    not_found_statuses = frozenset({404, 422})
    max_jobs = MAX_JOBS

    def fetch(self, board: str, company: str) -> list[Posting]:
        tenant, server, site = _parts(board)
        api = f"https://{tenant}.{server}.{HOST}/wday/cxs/{tenant}/{site}/jobs"

        def page(offset: int) -> dict:
            return self._post_json(board, api, {"limit": PAGE_SIZE, "offset": offset, "appliedFacets": {}, "searchText": ""})

        # Only the first page's total is reliable, so it sets how many more pages to read.
        first = page(0)
        jobs = list(first["jobPostings"])
        total = min(first.get("total") or 0, MAX_JOBS)
        with ThreadPoolExecutor(max_workers=PAGE_CONCURRENCY) as pool:
            for more in pool.map(page, range(PAGE_SIZE, total, PAGE_SIZE)):
                jobs += more["jobPostings"]

        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        seen: set[str] = set()
        postings = []
        for job in jobs:
            path = job.get("externalPath")
            if not path or path in seen:
                continue
            seen.add(path)
            postings.append(
                Posting(
                    source="workday",
                    board=board,
                    external_id=path,
                    title=job["title"],
                    company=company,
                    location=_location(job),
                    url=f"https://{tenant}.{server}.{HOST}/{site}{path}",
                    description="",
                    posted_at=_posted(job.get("postedOn"), today),
                    workplace_type=workplace_from_location(_location(job)),
                )
            )
        return postings

    def describe(self, posting: Posting) -> str:
        tenant, server, site = _parts(posting.board)
        details = self._get_json(posting.board, f"https://{tenant}.{server}.{HOST}/wday/cxs/{tenant}/{site}{posting.external_id}")
        return html_to_text((details.get("jobPostingInfo") or {}).get("jobDescription") or "")

    def board_candidates(self, company: str) -> list[str]:
        return []

    def default_name(self, board: str) -> str:
        return _parts(board)[0].replace("-", " ").title()

    def board_from_url(self, url: str) -> str | None:
        """https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/... -> nvidia.wd5/nvidiaexternalcareersite"""
        parsed = urlparse(url)
        labels = (parsed.hostname or "").lower().split(".")
        if len(labels) != 4 or ".".join(labels[2:]) != HOST or not re.fullmatch(r"wd\d+", labels[1]):
            return None
        segments = [s for s in parsed.path.lower().split("/") if s]
        if segments and LOCALE.match(segments[0]):
            segments = segments[1:]
        if not segments or segments[0] == "wday":
            return None
        board = f"{labels[0]}.{labels[1]}/{segments[0]}"
        return board if BOARD.match(board) else None

    def careers_url(self, board: str) -> str:
        tenant, server, site = _parts(board)
        return f"https://{tenant}.{server}.{HOST}/{site}"
