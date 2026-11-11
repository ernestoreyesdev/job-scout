import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.recruitee import RecruiteeSource

OFFER = {
    "id": 2800490,
    "title": "Data Scientist",
    "company_name": "bunq",
    "location": "Amsterdam, Noord-Holland, Netherlands",
    "careers_url": "https://careers.bunq.com/o/data-scientist",
    "published_at": "2026-10-28 13:21:58 UTC",
    "status": "published",
    "remote": False,
    "hybrid": True,
    "on_site": False,
    "description": "<p>Make life easy.</p>",
    "requirements": "<ul><li>XGBoost</li></ul>",
}


@respx.mock
def test_fetch_normalizes_published_offers():
    draft = {**OFFER, "id": 1, "status": "draft"}
    respx.get("https://bunq.recruitee.com/api/offers/").mock(
        return_value=httpx.Response(200, json={"offers": [OFFER, draft]})
    )

    [posting] = RecruiteeSource().fetch("bunq", "Bunq")

    assert (posting.source, posting.board, posting.external_id) == ("recruitee", "bunq", "2800490")
    assert posting.company == "bunq" and posting.url == OFFER["careers_url"]
    assert posting.description == "Make life easy.\n\n- XGBoost"
    assert posting.posted_at and posting.posted_at.isoformat() == "2026-10-28T13:21:58+00:00"
    assert posting.workplace_type == "hybrid"


@respx.mock
def test_unknown_board_raises():
    respx.get("https://nope.recruitee.com/api/offers/").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        RecruiteeSource().fetch("nope", "Nope")
