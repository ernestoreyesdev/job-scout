from datetime import datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

from app.sources.base import BOARD_SLUG, JobSource, Posting
from app.sources.text import html_to_text, join_locations, workplace_from_location

HOSTS = ("jobs.personio.de", "jobs.personio.com")


def _description(position: ElementTree.Element) -> str:
    sections = position.findall("jobDescriptions/jobDescription")
    return "\n\n".join(
        "\n".join(part for part in (section.findtext("name", "").strip(), html_to_text(section.findtext("value", ""))) if part)
        for section in sections
    )


def _posted(stamp: str | None) -> datetime | None:
    return datetime.fromisoformat(stamp) if stamp else None


class PersonioSource(JobSource):
    """
    Personio XML job feed: one request returns every position. Descriptions
    come only in the language each job was written in, so the English feed is
    read first and the default feed fills in jobs it left without one. Each
    company's board is a subdomain, {board}.jobs.personio.de, rather than a path.
    """

    name = "personio"
    label = "Personio"
    board_hosts = HOSTS
    reserved_paths = frozenset({"www", "api", "app"})

    def fetch(self, board: str, company: str) -> list[Posting]:
        positions = self._positions(board, {"language": "en"})
        if any(not _description(position) for position in positions):
            fallback = {position.findtext("id"): position for position in self._positions(board, {})}
            positions = [
                position if _description(position) else fallback.get(position.findtext("id"), position)
                for position in positions
            ]
        return [
            Posting(
                source="personio",
                board=board,
                external_id=position.findtext("id", ""),
                title=position.findtext("name", "").strip(),
                company=company,
                location=join_locations(
                    position.findtext("office"), *(office.text for office in position.findall("additionalOffices/office"))
                ),
                url=f"https://{board}.{HOSTS[0]}/job/{position.findtext('id')}",
                description=_description(position),
                posted_at=_posted(position.findtext("createdAt")),
                workplace_type=workplace_from_location(position.findtext("office")),
            )
            for position in positions
        ]

    def _positions(self, board: str, params: dict[str, str]) -> list[ElementTree.Element]:
        return ElementTree.fromstring(
            self._get_text(board, f"https://{board}.{HOSTS[0]}/xml", params).encode()
        ).findall("position")

    def board_from_url(self, url: str) -> str | None:
        host = (urlparse(url).hostname or "").lower()
        suffix = next((f".{h}" for h in HOSTS if host.endswith(f".{h}")), None)
        if suffix is None:
            return None
        board = host.removesuffix(suffix)
        return board if BOARD_SLUG.match(board) and board not in self.reserved_paths else None

    def careers_url(self, board: str) -> str:
        return f"https://{board}.{HOSTS[0]}/"
