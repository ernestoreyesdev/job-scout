from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import html_to_text, workplace_from_location

HOST = "pinpointhq.com"
WORKPLACES: dict[str, WorkplaceType] = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on_site": "onsite"}
# Description sections in page order, each with the field holding its heading.
SECTIONS = (
    ("description", None),
    ("key_responsibilities", "key_responsibilities_header"),
    ("skills_knowledge_expertise", "skills_knowledge_expertise_header"),
    ("benefits", "benefits_header"),
)


def _description(job: dict) -> str:
    parts = []
    for field, header in SECTIONS:
        if text := html_to_text(job.get(field) or ""):
            heading = job.get(header) if header else None
            parts.append(f"{heading}\n{text}" if heading else text)
    return "\n\n".join(parts)


def _location(job: dict) -> str | None:
    location = job.get("location") or {}
    return location.get("name") or ", ".join(p for p in (location.get("city"), location.get("province")) if p) or None


class PinpointSource(JobSource):
    """
    Pinpoint careers site feed: one request returns every job with its
    description. Each company's board is the subdomain {board}.pinpointhq.com.
    """

    name = "pinpoint"
    label = "Pinpoint"
    board_hosts = (HOST,)
    subdomain_boards = True
    reserved_paths = frozenset({"www", "app", "api", "help", "support", "blog"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        data = self._get_json(board, f"https://{board}.{HOST}/postings.json")
        return [
            Posting(
                source="pinpoint",
                board=board,
                external_id=str(job["id"]),
                title=job["title"],
                company=company,
                location=_location(job),
                url=job["url"],
                description=_description(job),
                posted_at=None,
                workplace_type=WORKPLACES.get(job.get("workplace_type") or "") or workplace_from_location(_location(job)),
            )
            for job in data["data"]
        ]

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOST}/"
