import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time
from urllib.parse import urlparse

from app.sources.base import BoardNotFound, JobSource, Posting
from app.sources.text import html_to_text, workplace_from_location

DOMAIN = "oraclecloud.com"
API = "hcmRestApi/resources/latest"
PAGE_SIZE = 200
MAX_JOBS = 2000
PAGE_CONCURRENCY = 4
BOARD = re.compile(r"^(?P<host>[a-z0-9-]+\.fa(?:\.[a-z0-9-]+)?)/(?P<site>[a-z0-9_]+)$")
HOST = re.compile(r"^[a-z0-9-]+\.fa(?:\.[a-z0-9-]+)?$")
SITE = re.compile(r"/sites/([a-z0-9_]+)(?:/|$)")
DESCRIPTION_FIELDS = ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr")


def _parts(board: str) -> tuple[str, str]:
    match = BOARD.match(board)
    if not match:
        raise BoardNotFound(f"Oracle board '{board}' isn't in tenant.fa/site form.")
    return f"{match['host']}.{DOMAIN}", match["site"]


def _posted(day: str | None) -> datetime | None:
    return datetime.combine(date.fromisoformat(day), time(), UTC) if day else None


class OracleSource(JobSource):
    """
    Oracle Recruiting Cloud career sites, through the JSON endpoint their pages
    call. A board is the host and site number, e.g. 'jpmc.fa/cx_1001'. Lists
    come newest first without descriptions, so describe() fetches one job's.
    """

    name = "oracle"
    label = "Oracle"
    board_hosts = (DOMAIN,)
    max_jobs = MAX_JOBS
    max_requests = 8

    def fetch(self, board: str, company: str) -> list[Posting]:
        host, site = _parts(board)

        def page(offset: int) -> dict:
            finder = f"findReqs;siteNumber={site.upper()},limit={PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC"
            url = f"https://{host}/{API}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList&finder={finder}"
            return self._get_json(board, url)["items"][0]

        first = page(0)
        jobs = list(first["requisitionList"])
        total = min(first.get("TotalJobsCount") or 0, MAX_JOBS)
        with ThreadPoolExecutor(max_workers=PAGE_CONCURRENCY) as pool:
            for more in pool.map(page, range(PAGE_SIZE, total, PAGE_SIZE)):
                jobs += more["requisitionList"]

        seen: set[str] = set()
        postings = []
        for job in jobs:
            if job["Id"] in seen:
                continue
            seen.add(job["Id"])
            postings.append(
                Posting(
                    source="oracle",
                    board=board,
                    external_id=job["Id"],
                    title=job["Title"],
                    company=company,
                    location=job.get("PrimaryLocation") or None,
                    url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site.upper()}/job/{job['Id']}",
                    description="",
                    posted_at=_posted(job.get("PostedDate")),
                    workplace_type=workplace_from_location(job.get("WorkplaceType") or job.get("PrimaryLocation")),
                )
            )
        return postings

    def describe(self, posting: Posting) -> str:
        host, site = _parts(posting.board)
        finder = f'ById;Id="{posting.external_id}",siteNumber={site.upper()}'
        data = self._get_json(posting.board, f"https://{host}/{API}/recruitingCEJobRequisitionDetails?onlyData=true&expand=all&finder={finder}")
        job = (data.get("items") or [{}])[0]
        return "\n\n".join(html_to_text(job[field]) for field in DESCRIPTION_FIELDS if job.get(field))

    def board_candidates(self, company: str) -> list[str]:
        return []

    def default_name(self, board: str) -> str:
        return _parts(board)[0].split(".")[0].replace("-", " ").title()

    def board_from_url(self, url: str) -> str | None:
        """https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/123 -> jpmc.fa/cx_1001"""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host.endswith(f".{DOMAIN}") or not HOST.match(host.removesuffix(f".{DOMAIN}")):
            return None
        site = SITE.search(parsed.path.lower())
        return f"{host.removesuffix(f'.{DOMAIN}')}/{site[1]}" if site else None

    def careers_url(self, board: str) -> str:
        host, site = _parts(board)
        return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site.upper()}"
