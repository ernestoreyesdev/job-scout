import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from app.sources.base import JobSource, Posting, WorkplaceType
from app.sources.text import html_to_text, join_locations

HOST = "teamtailor.com"
TT = "{https://teamtailor.com/locations}"
WORKPLACES: dict[str, WorkplaceType] = {"fully": "remote", "hybrid": "hybrid"}


class TeamtailorSource(JobSource):
    """
    Teamtailor career site RSS feed: one request returns every job with its
    description. Each company's board is the subdomain {board}.teamtailor.com;
    companies on their own domain aren't read.
    """

    name = "teamtailor"
    label = "Teamtailor"
    board_hosts = (HOST,)
    subdomain_boards = True
    reserved_paths = frozenset({"www", "app", "api", "support", "career", "careers", "blog", "status"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        channel = ET.fromstring(self._get_text(board, f"https://{board}.{HOST}/jobs.rss")).find("channel")
        items = channel.findall("item") if channel is not None else []
        name = (channel.findtext("title") if channel is not None else None) or company
        return [
            Posting(
                source=self.name,
                board=board,
                external_id=item.findtext("guid") or item.findtext("link") or "",
                title=item.findtext("title") or "",
                company=name,
                location=join_locations(*(place.findtext(f"{TT}name") for place in item.iter(f"{TT}location"))),
                url=item.findtext("link") or "",
                description=html_to_text(item.findtext("description") or ""),
                posted_at=parsedate_to_datetime(date) if (date := item.findtext("pubDate")) else None,
                workplace_type=WORKPLACES.get(item.findtext("remoteStatus") or ""),
            )
            for item in items
        ]

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOST}/jobs"
