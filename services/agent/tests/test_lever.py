import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.lever import API, LeverSource

JOB = {
    "id": "6ed76ce8-4156-4b60-b120-403538bd66cd",
    "text": "Backend Engineer",
    "hostedUrl": "https://jobs.lever.co/acme/6ed76ce8-4156-4b60-b120-403538bd66cd",
    "createdAt": 1786469891368,
    "categories": {"location": "New York, NY", "team": "Engineering", "allLocations": ["New York, NY", "Austin, TX"]},
    "workplaceType": "unspecified",
    "descriptionPlain": "We build payments.\n",
    "lists": [{"text": "What you'll do", "content": "<li>Ship APIs</li><li>Own services</li>"}],
    "additionalPlain": "Equal opportunity employer.",
}


@respx.mock
def test_fetch_normalizes_jobs():
    respx.get(f"{API}/acme").mock(return_value=httpx.Response(200, json=[JOB]))

    [posting] = LeverSource().fetch("acme", "Acme")

    assert posting.source == "lever"
    assert posting.board == "acme"
    assert posting.external_id == JOB["id"]
    assert posting.title == "Backend Engineer"
    assert posting.company == "Acme"
    assert posting.location == "New York, NY; Austin, TX"
    assert posting.workplace_type is None
    assert posting.url == JOB["hostedUrl"]
    assert posting.description == (
        "We build payments.\n\nWhat you'll do\n- Ship APIs\n- Own services\n\nEqual opportunity employer."
    )
    assert posting.posted_at.year == 2026


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        LeverSource().fetch("nope", "Nope")


@respx.mock
def test_the_country_code_is_named_on_the_main_location():
    job = {**JOB, "country": "IN", "categories": {"location": "Bengaluru"}}
    respx.get(f"{API}/acme").mock(return_value=httpx.Response(200, json=[job]))

    [posting] = LeverSource().fetch("acme", "Acme")

    assert posting.location == "Bengaluru, India"
