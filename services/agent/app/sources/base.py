import re
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

SourceName = Literal["greenhouse", "lever", "ashby"]
WorkplaceType = Literal["onsite", "hybrid", "remote"]

WORKPLACE_LABELS: dict[str, str] = {"onsite": "on-site", "hybrid": "hybrid", "remote": "remote"}

US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california", "co": "colorado",
    "ct": "connecticut", "de": "delaware", "dc": "district of columbia", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland", "ma": "massachusetts", "mi": "michigan",
    "mn": "minnesota", "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee", "tx": "texas",
    "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming",
}


class Posting(BaseModel):
    """A job posting normalized across sources; mirrors the postings table."""

    source: SourceName
    board: str
    external_id: str
    title: str
    company: str
    location: str | None
    url: str
    description: str
    posted_at: datetime | None
    workplace_type: WorkplaceType | None = None


class BoardNotFound(Exception):
    pass


class CompanyNotFound(Exception):
    pass


class JobSource(Protocol):
    name: SourceName

    def fetch(self, board: str, company: str) -> list[Posting]:
        """Open postings on `board`; `company` names them when the source doesn't."""
        ...


def matches_keywords(posting: Posting, keywords: list[str]) -> bool:
    """True when any keyword appears in the title or location; no keywords matches everything."""
    if not keywords:
        return True
    haystack = f"{posting.title} {posting.location or ''}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def join_locations(*locations: str | None) -> str | None:
    """Distinct locations in order, joined with '; '."""
    seen: list[str] = []
    for location in locations:
        if location and location.strip() and location.strip() not in seen:
            seen.append(location.strip())
    return "; ".join(seen) or None


def workplace_from_location(location: str | None) -> WorkplaceType | None:
    """For sources without a workplace field: 'Remote - US' is remote, 'Hybrid (NYC)' is hybrid."""
    text = (location or "").lower()
    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    return None


def matches_workplace(posting: Posting, workplace_types: list[str]) -> bool:
    """
    No types matches everything. A job whose type the source doesn't state
    has an office location, so it counts as on-site or hybrid but not remote.
    """
    if not workplace_types:
        return True
    if posting.workplace_type is None:
        return "onsite" in workplace_types or "hybrid" in workplace_types
    return posting.workplace_type in workplace_types


def matches_location(posting: Posting, location: str | None) -> bool:
    """
    City or state text against the posting's locations; 'Florida' also matches
    'FL' and the reverse. Locations are taken as US places, so a remote job
    matches when it's open to the US.
    """
    if not location:
        return True
    if posting.workplace_type == "remote":
        return remote_in_us(posting.location)
    text = (posting.location or "").lower()
    query = " ".join(location.lower().split())
    if query in US_STATES:
        abbreviation, name = query, US_STATES[query]
    else:
        abbreviation = next((code for code, state in US_STATES.items() if state == query), None)
        name = query
    if name in text:
        return True
    return abbreviation is not None and abbreviation in re.findall(r"[a-z]+", text)


def remote_in_us(location: str | None) -> bool:
    """
    True for remote locations open to the US: no country named ('Remote',
    'Anywhere'), the US itself, or a US state ('Remote - FL'). State codes
    count only in capitals so 'in' or 'or' in prose don't match.
    """
    lowered = (location or "").lower()
    words = set(re.findall(r"[a-z]+", lowered)) - {"remote", "anywhere", "worldwide", "global", "only", "based", "from", "the"}
    if not words or words & {"us", "usa"} or "united states" in lowered or "north america" in lowered:
        return True
    if any(state in lowered for state in US_STATES.values()):
        return True
    return any(code.lower() in US_STATES for code in re.findall(r"\b[A-Z]{2}\b", location or ""))
