import httpx
import pytest
import respx

from app.sources import board_from_url
from app.sources.bamboohr import BambooHRSource
from app.sources.base import BoardNotFound

LIST = "https://hubstaff.bamboohr.com/careers/list"

JOB = {
    "id": "22",
    "jobOpeningName": "Financial Analyst",
    "location": {"city": "Ottawa", "state": "Ontario"},
    "atsLocation": {"country": None, "state": None, "province": None, "city": None},
    "isRemote": None,
    "locationType": "0",
}


@respx.mock
def test_fetch_normalizes_jobs():
    remote = {**JOB, "id": "23", "location": {"city": "Austin", "state": "Austin"}, "isRemote": True}
    respx.get(LIST).mock(return_value=httpx.Response(200, json={"meta": {"totalCount": 2}, "result": [JOB, remote]}))

    office, anywhere = BambooHRSource().fetch("hubstaff", "Hubstaff")

    assert (office.source, office.board, office.external_id) == ("bamboohr", "hubstaff", "22")
    assert office.company == "Hubstaff" and office.url == "https://hubstaff.bamboohr.com/careers/22"
    assert office.location == "Ottawa, Ontario" and office.workplace_type is None
    assert office.description == "" and office.posted_at is None
    assert anywhere.location == "Austin" and anywhere.workplace_type == "remote"


@respx.mock
def test_describe_reads_the_job_details():
    respx.get("https://hubstaff.bamboohr.com/careers/22/detail").mock(
        return_value=httpx.Response(200, json={"result": {"jobOpening": {"description": "<p>Model the numbers.</p>"}}})
    )
    respx.get(LIST).mock(return_value=httpx.Response(200, json={"result": [JOB]}))
    source = BambooHRSource()
    [posting] = source.fetch("hubstaff", "Hubstaff")

    assert source.describe(posting) == "Model the numbers."


@respx.mock
@pytest.mark.parametrize("status", [302, 404])
def test_unknown_board_is_not_found(status: int):
    respx.get("https://nope.bamboohr.com/careers/list").mock(
        return_value=httpx.Response(status, headers={"location": "https://www.bamboohr.com/"})
    )

    with pytest.raises(BoardNotFound):
        BambooHRSource().fetch("nope", "Nope")


def test_boards_come_from_careers_pages():
    assert board_from_url("https://hubstaff.bamboohr.com/careers/21") == ("bamboohr", "hubstaff")
    assert board_from_url("https://www.bamboohr.com/careers/") is None
