import httpx
import pytest
import respx

from app.sources import oracle
from app.sources.base import BoardNotFound
from app.sources.oracle import OracleSource

LIST = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
DETAILS = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"


def page(total: int, ids: list[str]) -> httpx.Response:
    jobs = [
        {"Id": job_id, "Title": f"Engineer {job_id}", "PostedDate": "2026-11-25", "PrimaryLocation": "New York, NY, United States"}
        for job_id in ids
    ]
    return httpx.Response(200, json={"items": [{"TotalJobsCount": total, "requisitionList": jobs}]})


@respx.mock
def test_fetch_reads_every_page_newest_first(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(oracle, "PAGE_SIZE", 2)
    route = respx.get(url__startswith=LIST).mock(
        side_effect=lambda request: page(3, ["1", "2"]) if "offset=0" in str(request.url) else page(3, ["2", "3"])
    )

    postings = OracleSource().fetch("jpmc.fa/cx_1001", "JPMorganChase")

    assert [p.external_id for p in postings] == ["1", "2", "3"]
    assert "siteNumber=CX_1001" in str(route.calls[0].request.url)
    assert "sortBy=POSTING_DATES_DESC" in str(route.calls[0].request.url)
    first = postings[0]
    assert (first.source, first.board, first.company) == ("oracle", "jpmc.fa/cx_1001", "JPMorganChase")
    assert first.url == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/1"
    assert first.posted_at and first.posted_at.isoformat() == "2026-11-25T00:00:00+00:00"


@respx.mock
def test_describe_joins_the_description_fields():
    respx.get(url__startswith=LIST).mock(return_value=page(1, ["7"]))
    respx.get(url__startswith=DETAILS).mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"ExternalDescriptionStr": "<p>Build systems.</p>", "ExternalQualificationsStr": "<ul><li>Java</li></ul>"}]},
        )
    )
    source = OracleSource()
    [posting] = source.fetch("jpmc.fa/cx_1001", "JPMorganChase")

    assert source.describe(posting) == "Build systems.\n\n- Java"


def test_a_board_outside_the_tenant_site_form_is_not_found():
    with pytest.raises(BoardNotFound):
        OracleSource().fetch("jpmc", "JPMorganChase")
