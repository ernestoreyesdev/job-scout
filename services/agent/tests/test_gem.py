import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.gem import GemSource

API = "https://api.gem.com/job_board/v0"
JOB = {
    "id": "am9icG9zdDrLws",
    "title": "Software Engineer",
    "absolute_url": "https://jobs.gem.com/silkline/am9icG9zdDrLws",
    "content": "<h2>Overview</h2><p>Build procurement software.</p>",
    "first_published_at": "2025-08-15T16:37:19.191Z",
    "location": {"name": "Seattle, United States"},
    "location_type": "in_office",
    "offices": [
        {"name": "Seattle", "location": {"name": "Seattle, United States"}},
        {"name": "Chicago", "location": {"name": "Chicago, United States"}},
    ],
}


@respx.mock
def test_fetch_normalizes_job_posts():
    respx.get(f"{API}/silkline/job_posts/").mock(return_value=httpx.Response(200, json=[JOB]))

    [posting] = GemSource().fetch("silkline", "Silkline")

    assert (posting.source, posting.board, posting.external_id) == ("gem", "silkline", "am9icG9zdDrLws")
    assert posting.company == "Silkline" and posting.url == JOB["absolute_url"]
    assert posting.location == "Seattle, United States; Chicago, United States"
    assert posting.description == "Overview\nBuild procurement software."
    assert posting.posted_at and posting.posted_at.isoformat() == "2025-08-15T16:37:19.191000+00:00"
    assert posting.workplace_type == "onsite"


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope/job_posts/").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        GemSource().fetch("nope", "Nope")
