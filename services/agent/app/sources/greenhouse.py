import html
from html.parser import HTMLParser

import httpx

from app.sources.base import BoardNotFound, Posting, workplace_from_location

API = "https://boards-api.greenhouse.io/v1/boards"


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(content: str) -> str:
    """Greenhouse returns entity-escaped HTML; unescape it, then keep only the text."""
    parser = _TextExtractor()
    parser.feed(html.unescape(content))
    lines = (line.strip() for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


class GreenhouseSource:
    """Public Greenhouse job board API; no credentials needed."""

    name = "greenhouse"

    def __init__(self, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30)

    def fetch(self, board: str, company: str) -> list[Posting]:
        res = self._http.get(f"{API}/{board}/jobs", params={"content": "true"})
        if res.status_code == 404:
            raise BoardNotFound(f"Greenhouse board '{board}' does not exist.")
        res.raise_for_status()

        return [
            Posting(
                source="greenhouse",
                board=board,
                external_id=str(job["id"]),
                title=job["title"],
                company=job.get("company_name") or company,
                location=(job.get("location") or {}).get("name"),
                url=job["absolute_url"],
                description=html_to_text(job.get("content") or ""),
                posted_at=job.get("first_published") or job.get("updated_at"),
                workplace_type=workplace_from_location((job.get("location") or {}).get("name")),
            )
            for job in res.json()["jobs"]
        ]
