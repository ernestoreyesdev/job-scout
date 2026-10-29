import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.workable import API, WorkableSource

JOB = {
    "title": "ML Engineer",
    "shortcode": "81B46579FE",
    "telecommuting": True,
    "url": "https://apply.workable.com/j/81B46579FE",
    "published_on": "2026-05-29",
    "locations": [
        {"city": "Paris", "region": "Île-de-France", "country": "France"},
        {"city": "", "region": None, "country": "Germany"},
    ],
    "description": "<p>Train models &amp; ship.</p>",
}


@respx.mock
def test_fetch_normalizes_jobs():
    office = {**JOB, "shortcode": "OFFICE", "telecommuting": False}
    respx.get(f"{API}/acme").mock(
        return_value=httpx.Response(200, json={"name": "Acme AI", "description": "", "jobs": [JOB, office]})
    )

    remote, onsite = WorkableSource().fetch("acme", "acme")

    assert (remote.source, remote.board, remote.external_id) == ("workable", "acme", "81B46579FE")
    assert remote.company == "Acme AI"
    assert remote.location == "Paris, Île-de-France, France; Germany"
    assert remote.description == "Train models & ship."
    assert remote.posted_at.isoformat() == "2026-05-29T00:00:00+00:00"
    assert remote.workplace_type == "remote" and onsite.workplace_type is None


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        WorkableSource().fetch("nope", "Nope")
