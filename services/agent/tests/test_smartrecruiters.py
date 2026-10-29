import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.smartrecruiters import API, SmartRecruitersSource


def job(job_id: str, **location: object) -> dict:
    return {
        "id": job_id,
        "name": f"Engineer {job_id}",
        "company": {"identifier": "Acme", "name": "Acme Corp"},
        "releasedDate": "2026-10-29T16:27:56.866Z",
        "location": {"city": "Austin", "region": "TX", "country": "us", "remote": False, "hybrid": False, **location},
    }


def page(jobs: list[dict], total: int) -> httpx.Response:
    return httpx.Response(200, json={"offset": 0, "limit": 100, "totalFound": total, "content": jobs})


@respx.mock
def test_fetch_pages_through_every_posting():
    route = respx.get(f"{API}/acme/postings")
    route.side_effect = [page([job(str(i)) for i in range(100)], 101), page([job("100", remote=True)], 101)]

    postings = SmartRecruitersSource().fetch("acme", "Acme")

    assert len(postings) == 101
    assert [call.request.url.params["offset"] for call in route.calls] == ["0", "100"]
    first, last = postings[0], postings[-1]
    assert (first.source, first.board, first.company) == ("smartrecruiters", "acme", "Acme Corp")
    assert first.location == "Austin, TX, United States" and first.workplace_type == "onsite"
    assert first.url == "https://jobs.smartrecruiters.com/acme/0" and first.description == ""
    assert last.workplace_type == "remote"


@respx.mock
def test_a_company_without_postings_is_not_found():
    respx.get(f"{API}/nope/postings").mock(return_value=page([], 0))

    with pytest.raises(BoardNotFound):
        SmartRecruitersSource().fetch("nope", "Nope")


@respx.mock
def test_describe_joins_the_job_ad_sections():
    respx.get(f"{API}/acme/postings").mock(return_value=page([job("7", hybrid=True)], 1))
    respx.get(f"{API}/acme/postings/7").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobAd": {
                    "sections": {
                        "jobDescription": {"title": "Job Description", "text": "<p>Build APIs.</p>"},
                        "qualifications": {"title": "Qualifications", "text": "<ul><li>Python</li></ul>"},
                        "additionalInformation": {"title": "Additional Information", "text": ""},
                    }
                }
            },
        )
    )
    source = SmartRecruitersSource()
    [posting] = source.fetch("acme", "Acme")

    assert posting.workplace_type == "hybrid"
    assert source.describe(posting) == "Job Description\nBuild APIs.\n\nQualifications\n- Python"
