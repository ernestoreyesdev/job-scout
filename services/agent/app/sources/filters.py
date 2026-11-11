import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.sources.base import Posting

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

# Countries other than the US, by the names job locations use. Names shared with US towns
# (Georgia, Panama, Lebanon, Peru, Cuba, Jordan) are left out.
FOREIGN_COUNTRIES = (
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", "australia", "austria",
    "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium", "belize", "benin", "bhutan",
    "bolivia", "bosnia", "botswana", "brazil", "brunei", "bulgaria", "burkina faso", "burundi", "cambodia",
    "cameroon", "canada", "cape verde", "chile", "china", "colombia", "congo", "costa rica", "croatia", "cyprus",
    "czech", "czechia", "denmark", "djibouti", "dominican republic", "ecuador", "egypt", "el salvador", "england",
    "eritrea", "estonia", "eswatini", "ethiopia", "fiji", "finland", "france", "gabon", "gambia", "germany",
    "ghana", "greece", "guatemala", "guinea", "guyana", "haiti", "honduras", "hong kong", "hungary", "iceland",
    "india", "indonesia", "iran", "iraq", "ireland", "israel", "italy", "ivory coast", "jamaica", "japan",
    "kazakhstan", "kenya", "korea", "kosovo", "kuwait", "kyrgyzstan", "laos", "latvia", "lesotho", "liberia",
    "libya", "liechtenstein", "lithuania", "luxembourg", "macau", "madagascar", "malawi", "malaysia", "maldives",
    "mali", "malta", "mauritania", "mauritius", "mexico", "moldova", "monaco", "mongolia", "montenegro", "morocco",
    "mozambique", "myanmar", "namibia", "nepal", "netherlands", "new zealand", "nicaragua", "nigeria",
    "north macedonia", "northern ireland", "norway", "oman", "pakistan", "palestine", "paraguay", "philippines",
    "poland", "portugal", "qatar", "romania", "russia", "rwanda", "saudi arabia", "scotland", "senegal", "serbia",
    "sierra leone", "singapore", "slovakia", "slovenia", "somalia", "south africa", "south korea", "spain",
    "sri lanka", "sudan", "suriname", "sweden", "switzerland", "syria", "taiwan", "tajikistan", "tanzania",
    "thailand", "trinidad", "tunisia", "turkey", "turkiye", "uganda", "ukraine", "united arab emirates", "uae",
    "united kingdom", "uk", "uruguay", "uzbekistan", "venezuela", "vietnam", "wales", "yemen", "zambia", "zimbabwe",
    "emea", "apac", "latam",
)

# Large foreign job hubs that appear without a country. Checked after US states, so
# "Dublin, CA" or "Vienna, VA" stay in the US.
FOREIGN_CITIES = (
    "london", "dublin", "galway", "cork", "berlin", "munich", "hamburg", "frankfurt", "amsterdam", "madrid",
    "barcelona", "lisbon", "warsaw", "krakow", "wroclaw", "prague", "bratislava", "ljubljana", "bucharest",
    "budapest", "belgrade", "sofia", "athens", "istanbul", "riga", "vilnius", "tallinn", "kyiv", "stockholm",
    "oslo", "lysaker", "copenhagen", "helsinki", "zurich", "geneva", "vienna", "tel aviv", "toronto", "vancouver",
    "montreal", "ottawa", "calgary", "mexico city", "guadalajara", "sao paulo", "são paulo", "buenos aires",
    "bogota", "medellin", "santiago", "bangalore", "bengaluru", "hyderabad", "pune", "chennai", "mumbai", "delhi",
    "gurgaon", "gurugram", "noida", "tokyo", "seoul", "shanghai", "beijing", "shenzhen", "sydney", "melbourne",
    "manila", "paris",
)


def matches_keywords(posting: Posting, keywords: list[str]) -> bool:
    """
    True when any keyword appears in the title as whole words, plurals included:
    'engineer' matches 'Engineers' but not 'Engineering', 'java' not 'JavaScript'.
    No keywords matches everything.
    """
    return not keywords or any(keyword_pattern(keyword).search(posting.title) for keyword in keywords)


def matches_workplace(posting: Posting, workplace_types: Sequence[str]) -> bool:
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
    'FL' and the reverse. Searches are for US jobs: a remote job matches only
    when it's open to the US, and without a location any other job matches
    only when it's in the US.
    """
    if posting.workplace_type == "remote":
        return remote_in_us(posting.location)
    if not location:
        return in_us(posting.location)
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


@lru_cache(maxsize=256)
def keyword_pattern(keyword: str) -> re.Pattern[str]:
    """A keyword as whole words, each allowing an 's' or 'es' plural, separated by spaces, hyphens or slashes."""
    words = keyword.lower().split()
    body = r"[\s/-]+".join(re.escape(word) + r"(?:e?s)?" for word in words)
    return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)


def matches_exclusions(posting: Posting, exclude: list[str]) -> bool:
    """True when no excluded word or phrase appears in the title, matched like keywords."""
    return not any(keyword_pattern(word).search(posting.title) for word in exclude)


def posted_within(posting: Posting, days: int | None, now: datetime | None = None) -> bool:
    """True when the posting is no older than `days`; undated postings and no limit always pass."""
    if days is None or posting.posted_at is None:
        return True
    return posting.posted_at >= (now or datetime.now(UTC)) - timedelta(days=days)


def in_us(location: str | None) -> bool:
    """
    True when any of a posting's locations ('; '-separated) may be in the US:
    it names the US or a state, or it names no foreign country, foreign hub or
    trailing country code. 'Krakow, Poland' and 'Tienen, BE' are out; a bare
    'San Francisco' and 'Dublin, CA' are in.
    """
    if not location or not location.strip():
        return True
    return any(_place_in_us(place) for place in location.split(";"))


def _place_in_us(place: str) -> bool:
    lowered = place.lower()
    words = set(re.findall(r"[a-z]+", lowered))
    if words & {"us", "usa"} or "united states" in lowered or any(state in lowered for state in US_STATES.values()):
        return True
    if _names_any(lowered, FOREIGN_COUNTRIES):
        return False
    if any(code.lower() in US_STATES for code in re.findall(r"\b[A-Z]{2}\b", place)):
        return True
    if _names_any(lowered, FOREIGN_CITIES):
        return False
    last = place.split(",")[-1].strip()
    return not re.fullmatch(r"[A-Z]{2}", last)


def _names_any(lowered: str, places: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(place)}(?![a-z])", lowered) for place in places)
