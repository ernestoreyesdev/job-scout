import html
import json
import re
from html.parser import HTMLParser

from app.sources.base import WorkplaceType


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
    """Plain text of an HTML job description; entity-escaped HTML (as Greenhouse sends it) is unescaped first."""
    parser = _TextExtractor()
    parser.feed(html.unescape(content))
    lines = (line.strip() for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


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


# Country codes job systems send, named so they can't be read as US state codes (CA, IN, DE, GA...).
COUNTRY_NAMES = {
    "us": "United States", "ca": "Canada", "mx": "Mexico", "br": "Brazil", "ar": "Argentina", "cl": "Chile",
    "co": "Colombia", "pe": "Peru", "uy": "Uruguay", "cr": "Costa Rica", "pa": "Panama", "gb": "United Kingdom",
    "uk": "United Kingdom", "ie": "Ireland", "fr": "France", "de": "Germany", "es": "Spain", "pt": "Portugal",
    "it": "Italy", "nl": "Netherlands", "be": "Belgium", "ch": "Switzerland", "at": "Austria", "pl": "Poland",
    "cz": "Czechia", "sk": "Slovakia", "si": "Slovenia", "ro": "Romania", "hu": "Hungary", "bg": "Bulgaria",
    "gr": "Greece", "hr": "Croatia", "rs": "Serbia", "se": "Sweden", "no": "Norway", "dk": "Denmark",
    "fi": "Finland", "ee": "Estonia", "lt": "Lithuania", "lv": "Latvia", "ua": "Ukraine", "tr": "Turkey",
    "il": "Israel", "ae": "United Arab Emirates", "sa": "Saudi Arabia", "eg": "Egypt", "ma": "Morocco",
    "za": "South Africa", "ng": "Nigeria", "ke": "Kenya", "in": "India", "pk": "Pakistan", "bd": "Bangladesh",
    "lk": "Sri Lanka", "cn": "China", "hk": "Hong Kong", "tw": "Taiwan", "jp": "Japan", "kr": "South Korea",
    "sg": "Singapore", "my": "Malaysia", "id": "Indonesia", "ph": "Philippines", "vn": "Vietnam",
    "th": "Thailand", "au": "Australia", "nz": "New Zealand", "lu": "Luxembourg", "is": "Iceland",
    "al": "Albania", "me": "Montenegro", "ga": "Gabon", "ge": "Georgia (country)", "am": "Armenia",
    "az": "Azerbaijan", "kz": "Kazakhstan", "md": "Moldova", "mt": "Malta", "cy": "Cyprus",
}


def country_name(code: str | None) -> str | None:
    """'IN' -> 'India'; unknown codes are returned as given."""
    if not code or not code.strip():
        return None
    return COUNTRY_NAMES.get(code.strip().lower(), code.strip())


def with_country(location: str | None, country: str | None) -> str | None:
    """Appends the country to a location that doesn't already name it: ('Tokyo', 'Japan') -> 'Tokyo, Japan'."""
    if not location or not location.strip():
        return country
    if not country or country.lower() in location.lower():
        return location
    return f"{location.strip()}, {country}"


JSON_LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def job_posting_ld(page: str) -> dict:
    """The schema.org JobPosting a job page embeds as JSON-LD, or {} when it has none."""
    for block in JSON_LD.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}
