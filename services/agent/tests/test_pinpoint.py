import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.pinpoint import PinpointSource

JOB = {
    "id": "496135",
    "title": "Backend Engineer",
    "url": "https://prophetexchange.pinpointhq.com/en/postings/5d226f78",
    "description": "<p>Build markets.</p>",
    "key_responsibilities": "<ul><li>Ship APIs</li></ul>",
    "key_responsibilities_header": "WHAT YOU'LL DO",
    "skills_knowledge_expertise": "",
    "skills_knowledge_expertise_header": "WHAT YOU BRING",
    "benefits": "<p>Equity</p>",
    "benefits_header": None,
    "workplace_type": "remote",
    "location": {"name": "Remote - USA", "city": "New York", "province": "New York"},
}


@respx.mock
def test_fetch_joins_description_sections():
    respx.get("https://prophetexchange.pinpointhq.com/postings.json").mock(
        return_value=httpx.Response(200, json={"data": [JOB]})
    )

    [posting] = PinpointSource().fetch("prophetexchange", "ProphetX")

    assert (posting.source, posting.board, posting.external_id) == ("pinpoint", "prophetexchange", "496135")
    assert posting.company == "ProphetX" and posting.url == JOB["url"]
    assert posting.description == "Build markets.\n\nWHAT YOU'LL DO\n- Ship APIs\n\nEquity"
    assert posting.location == "Remote - USA" and posting.workplace_type == "remote"


@respx.mock
def test_unknown_board_raises():
    respx.get("https://nope.pinpointhq.com/postings.json").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        PinpointSource().fetch("nope", "Nope")
