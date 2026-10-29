import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.sources import board_from_url
from app.sources.base import BoardNotFound
from app.sources.workday import MAX_JOBS, WorkdaySource, _location, _posted

BOARD = "acme.wd5/acmecareers"
LIST = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/acmecareers/jobs"


def job(n: int, **fields: object) -> dict:
    return {
        "title": f"Engineer {n}",
        "externalPath": f"/job/US-TX-Austin/Engineer_{n}",
        "locationsText": "US, TX, Austin",
        "postedOn": "Posted Today",
        **fields,
    }


def listing(request: httpx.Request, total: int) -> httpx.Response:
    offset = json.loads(request.content)["offset"]
    jobs = [job(n) for n in range(offset, min(offset + 20, total))]
    return httpx.Response(200, json={"total": total, "jobPostings": jobs})


@respx.mock
def test_fetch_reads_every_page_and_normalizes_jobs():
    route = respx.post(LIST).mock(side_effect=lambda request: listing(request, 45))

    postings = WorkdaySource().fetch(BOARD, "Acme")

    assert len(postings) == 45
    assert sorted(json.loads(call.request.content)["offset"] for call in route.calls) == [0, 20, 40]
    first = postings[0]
    assert (first.source, first.board, first.external_id) == ("workday", BOARD, "/job/US-TX-Austin/Engineer_0")
    assert first.url == "https://acme.wd5.myworkdayjobs.com/acmecareers/job/US-TX-Austin/Engineer_0"
    assert first.description == "" and first.location == "US, TX, Austin" and first.workplace_type is None


@respx.mock
def test_fetch_stops_at_the_query_limit():
    route = respx.post(LIST).mock(side_effect=lambda request: listing(request, 5000))

    postings = WorkdaySource().fetch(BOARD, "Acme")

    assert len(postings) == MAX_JOBS and len(route.calls) == MAX_JOBS // 20


@respx.mock
def test_fetch_skips_repeats_and_jobs_without_a_path():
    jobs = [job(1), job(1), {"bulletFields": ["JR1"]}, job(2, locationsText="US, CA, Remote")]
    respx.post(LIST).mock(return_value=httpx.Response(200, json={"total": 4, "jobPostings": jobs}))

    postings = WorkdaySource().fetch(BOARD, "Acme")

    assert [p.title for p in postings] == ["Engineer 1", "Engineer 2"]
    assert postings[1].workplace_type == "remote"


@respx.mock
@pytest.mark.parametrize("status", [404, 422])
def test_unknown_site_or_company_is_not_found(status: int):
    respx.post(LIST).mock(return_value=httpx.Response(status))

    with pytest.raises(BoardNotFound):
        WorkdaySource().fetch(BOARD, "Acme")


def test_a_malformed_board_is_not_found():
    with pytest.raises(BoardNotFound):
        WorkdaySource().fetch("acme", "Acme")


@respx.mock
def test_describe_reads_the_job_details():
    respx.post(LIST).mock(side_effect=lambda request: listing(request, 1))
    respx.get("https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/acmecareers/job/US-TX-Austin/Engineer_0").mock(
        return_value=httpx.Response(200, json={"jobPostingInfo": {"jobDescription": "<p>Build &amp; ship.</p>"}})
    )
    source = WorkdaySource()
    [posting] = source.fetch(BOARD, "Acme")

    assert source.describe(posting) == "Build & ship."


def test_relative_posting_dates():
    today = datetime(2026, 10, 29, tzinfo=UTC)

    assert _posted("Posted Today", today) == today
    assert _posted("Posted Yesterday", today) == datetime(2026, 10, 28, tzinfo=UTC)
    assert _posted("Posted 3 Days Ago", today) == datetime(2026, 10, 26, tzinfo=UTC)
    assert _posted("Posted 30+ Days Ago", today) == datetime(2026, 9, 29, tzinfo=UTC)
    assert _posted("", today) is None


def test_boards_come_from_career_site_urls():
    assert board_from_url("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/X_JR1") == (
        "workday",
        "nvidia.wd5/nvidiaexternalcareersite",
    )
    assert board_from_url("https://acme.wd1.myworkdayjobs.com/External") == ("workday", "acme.wd1/external")
    assert board_from_url("https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/External/jobs") is None
    assert board_from_url("https://www.myworkdayjobs.com/acme") is None


def test_names_and_lookup():
    source = WorkdaySource()

    assert source.default_name("scale-ai.wd1/careers") == "Scale Ai"
    assert source.board_candidates("NVIDIA") == []


def test_jobs_in_several_places_use_the_main_location_from_their_path():
    several = job(1, locationsText="6 Locations", externalPath="/job/US-CA-Santa-Clara-Remote/Engineer_1")
    unknown = job(2, locationsText="3 Locations", externalPath="/details/Engineer_2")

    assert _location(several) == "US CA Santa Clara Remote and 5 more"
    assert _location(unknown) == "3 Locations"
    assert _location(job(3)) == "US, TX, Austin"
