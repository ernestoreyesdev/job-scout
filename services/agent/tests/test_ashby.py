import httpx
import pytest
import respx

from app.sources.ashby import API, AshbySource
from app.sources.base import BoardNotFound

JOB = {
    "id": "240d459b-696d-43eb-8497-fab3e56ecd9b",
    "title": "Research Engineer",
    "location": "San Francisco",
    "jobUrl": "https://jobs.ashbyhq.com/acme/240d459b-696d-43eb-8497-fab3e56ecd9b",
    "publishedAt": "2025-04-05T00:03:20.653+00:00",
    "descriptionPlain": "Train models.",
    "isListed": True,
    "workplaceType": "Hybrid",
    "secondaryLocations": [{"location": "New York, New York"}, {"location": "San Francisco"}],
}


@respx.mock
def test_fetch_normalizes_listed_jobs():
    unlisted = {**JOB, "id": "hidden", "isListed": False}
    respx.get(f"{API}/acme").mock(return_value=httpx.Response(200, json={"jobs": [JOB, unlisted], "apiVersion": "1"}))

    [posting] = AshbySource().fetch("acme", "Acme")

    assert posting.source == "ashby"
    assert posting.board == "acme"
    assert posting.external_id == JOB["id"]
    assert posting.company == "Acme"
    assert posting.location == "San Francisco; New York, New York"
    assert posting.workplace_type == "hybrid"
    assert posting.url == JOB["jobUrl"]
    assert posting.description == "Train models."
    assert posting.posted_at.isoformat() == "2025-04-05T00:03:20.653000+00:00"


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        AshbySource().fetch("nope", "Nope")


@respx.mock
def test_each_location_gets_its_address_country():
    job = {
        **JOB,
        "location": "Tokyo",
        "address": {"postalAddress": {"addressCountry": "Japan"}},
        "secondaryLocations": [{"location": "Austin, TX", "address": {"postalAddress": {"addressCountry": "United States"}}}],
    }
    respx.get(f"{API}/acme").mock(return_value=httpx.Response(200, json={"jobs": [job]}))

    [posting] = AshbySource().fetch("acme", "Acme")

    assert posting.location == "Tokyo, Japan; Austin, TX, United States"
