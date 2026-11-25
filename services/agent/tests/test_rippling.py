import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.rippling import RipplingSource

API = "https://api.rippling.com/platform/api/ats/v1/board"
JOB = {
    "uuid": "5a158024",
    "name": "Business Development Associate",
    "url": "https://ats.rippling.com/etc/jobs/5a158024",
    "workLocation": {"label": "Remote (US)", "id": "Remote (US)"},
}


@respx.mock
def test_fetch_lists_jobs_and_describe_reads_one():
    respx.get(f"{API}/etc/jobs").mock(return_value=httpx.Response(200, json=[JOB]))
    respx.get(f"{API}/etc/jobs/5a158024").mock(
        return_value=httpx.Response(200, json={"description": {"company": "<p>About etc.</p>", "role": "<ul><li>Sell</li></ul>"}})
    )
    source = RipplingSource()

    [posting] = source.fetch("etc", "etc.")

    assert (posting.source, posting.board, posting.external_id) == ("rippling", "etc", "5a158024")
    assert posting.title == "Business Development Associate" and posting.url == JOB["url"]
    assert posting.location == "Remote (US)" and posting.workplace_type == "remote"
    assert posting.description == "" and posting.posted_at is None
    assert source.describe(posting) == "About etc.\n\n- Sell"


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope/jobs").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        RipplingSource().fetch("nope", "Nope")
