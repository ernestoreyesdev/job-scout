import httpx
import pytest
import respx

from app.sources.base import BoardNotFound, Posting, matches_keywords
from app.sources.greenhouse import API, GreenhouseSource, html_to_text

JOB = {
    "id": 5456619008,
    "title": "Senior Software Engineer",
    "company_name": "Acme",
    "location": {"name": "Remote, US"},
    "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/5456619008",
    "first_published": "2026-10-19T11:17:24-04:00",
    "updated_at": "2026-10-20T09:00:00-04:00",
    "content": "&lt;h2&gt;About&lt;/h2&gt;&lt;p&gt;Build things &amp;amp; ship.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;",
}


@respx.mock
def test_fetch_normalizes_jobs():
    respx.get(f"{API}/acme/jobs").mock(return_value=httpx.Response(200, json={"jobs": [JOB], "meta": {"total": 1}}))

    [posting] = GreenhouseSource().fetch("acme", "acme inc")

    assert posting.source == "greenhouse"
    assert posting.board == "acme"
    assert posting.external_id == "5456619008"
    assert posting.company == "Acme"
    assert posting.location == "Remote, US"
    assert posting.workplace_type == "remote"
    assert posting.description == "About\nBuild things & ship.\n- Python"
    assert posting.posted_at.isoformat() == "2026-10-19T11:17:24-04:00"


@respx.mock
def test_fetch_falls_back_to_given_company_name():
    job = {**JOB, "company_name": None, "location": None, "first_published": None}
    respx.get(f"{API}/acme/jobs").mock(return_value=httpx.Response(200, json={"jobs": [job]}))

    [posting] = GreenhouseSource().fetch("acme", "Acme Inc")

    assert posting.company == "Acme Inc"
    assert posting.location is None
    assert posting.posted_at.isoformat() == "2026-10-20T09:00:00-04:00"


@respx.mock
def test_unknown_board_raises():
    respx.get(f"{API}/nope/jobs").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        GreenhouseSource().fetch("nope", "Nope")


def test_html_to_text_drops_tags_and_blank_lines():
    assert html_to_text("&lt;div&gt;&lt;p&gt;One&lt;/p&gt;&lt;br&gt;&lt;p&gt;Two&lt;/p&gt;&lt;/div&gt;") == "One\nTwo"


def _posting(title: str, location: str | None) -> Posting:
    return Posting(
        source="greenhouse",
        board="acme",
        external_id="1",
        title=title,
        company="Acme",
        location=location,
        url="https://example.com",
        description="",
        posted_at=None,
    )


def test_keywords_match_title_or_location_case_insensitively():
    posting = _posting("Senior Software Engineer", "Remote, US")

    assert matches_keywords(posting, [])
    assert matches_keywords(posting, ["engineer"])
    assert matches_keywords(posting, ["designer", "REMOTE"])
    assert not matches_keywords(posting, ["designer"])
    assert not matches_keywords(_posting("Designer", None), ["remote"])
