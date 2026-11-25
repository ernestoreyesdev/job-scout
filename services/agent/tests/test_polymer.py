import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.polymer import PolymerSource

API = "https://api.polymer.co/v1/hire/organizations"


def job(job_id: int) -> dict:
    return {
        "id": job_id,
        "title": "BESS Asset Manager",
        "organization_name": "Return",
        "display_location": "Amsterdam, NL",
        "job_post_url": f"https://jobs.polymer.co/return/{job_id}",
        "published_at": "2026-11-23T09:23:36.151Z",
        "remoteness_pretty": "Hybrid",
    }


@respx.mock
def test_fetch_pages_through_jobs_and_describe_reads_one():
    respx.get(f"{API}/return/jobs", params={"page": 1}).mock(
        return_value=httpx.Response(200, json={"items": [job(1)], "meta": {"is_last": False}})
    )
    respx.get(f"{API}/return/jobs", params={"page": 2}).mock(
        return_value=httpx.Response(200, json={"items": [job(2)], "meta": {"is_last": True}})
    )
    respx.get(f"{API}/return/jobs/1").mock(return_value=httpx.Response(200, json={"description": "<p>Run batteries.</p>"}))
    source = PolymerSource()

    postings = source.fetch("return", "return")

    assert [p.external_id for p in postings] == ["1", "2"]
    first = postings[0]
    assert (first.source, first.board, first.company) == ("polymer", "return", "Return")
    assert first.location == "Amsterdam, NL" and first.workplace_type == "hybrid"
    assert first.posted_at and first.posted_at.isoformat() == "2026-11-23T09:23:36.151000+00:00"
    assert source.describe(first) == "Run batteries."


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope/jobs").mock(return_value=httpx.Response(422))

    with pytest.raises(BoardNotFound):
        PolymerSource().fetch("nope", "Nope")
