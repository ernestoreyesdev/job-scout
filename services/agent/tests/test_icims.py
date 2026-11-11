import httpx
import pytest
import respx

from app.sources import board_from_url
from app.sources.base import BoardNotFound
from app.sources.icims import ICIMSSource, _place

SEARCH = "https://careers-gdms.icims.com/jobs/search"


def card(job_id: int, title: str, location: str, posted: str | None = None) -> str:
    when = f'<span class="sr-only field-label">Posted Date</span>\n<span title="{posted}">1 hour ago</span>' if posted else ""
    return f"""
<li class="iCIMS_JobCardItem">
<div class="col-xs-6 header right">{when}</div>
<div class="col-xs-12 title">
<a href="https://careers-gdms.icims.com/jobs/{job_id}/role/job?in_iframe=1" class="iCIMS_Anchor" title="{job_id} - {title}">
<span class="sr-only field-label">Title</span>
<h3 >
{title}</h3>
</a>
</div>
<dt class="iCIMS_JobHeaderField"><span class="sr-only field-label">Job Location</span>
</dt>
<dd class="iCIMS_JobHeaderData"><span >
{location}</span>
</dd>
</li>"""


def page(total: int, *cards: str) -> httpx.Response:
    return httpx.Response(200, text=f"<h2>Page 1 of {total}</h2><ul>{''.join(cards)}</ul>")


@respx.mock
def test_fetch_reads_every_page_and_normalizes_cards():
    respx.get(SEARCH, params={"pr": "0"}).mock(
        return_value=page(2, card(76097, "Software Engineer &amp; Lead", "US-MA-Pittsfield", "11/2/2026 12:00 PM"))
    )
    respx.get(SEARCH, params={"pr": "1"}).mock(return_value=page(2, card(76104, "Data Engineer", "US-Remote")))

    first, second = ICIMSSource().fetch("careers-gdms", "GDMS")

    assert (first.source, first.board, first.external_id) == ("icims", "careers-gdms", "76097")
    assert first.title == "Software Engineer & Lead" and first.company == "GDMS"
    assert first.url == "https://careers-gdms.icims.com/jobs/76097/role/job"
    assert first.location == "Pittsfield, MA, United States"
    assert first.posted_at and first.posted_at.isoformat() == "2026-11-02T12:00:00+00:00"
    assert second.location == "Remote, United States" and second.workplace_type == "remote" and second.posted_at is None


@respx.mock
def test_describe_reads_the_job_page_json_ld():
    page_html = '<script type="application/ld+json">{"@type": "JobPosting", "description": "<p>Build systems.</p>"}</script>'
    respx.get("https://careers-gdms.icims.com/jobs/76097/role/job").mock(return_value=httpx.Response(200, text=page_html))
    respx.get(SEARCH).mock(return_value=page(1, card(76097, "Engineer", "US-MA-Pittsfield")))
    source = ICIMSSource()
    [posting] = source.fetch("careers-gdms", "GDMS")

    assert source.describe(posting) == "Build systems."


@respx.mock
def test_unknown_board_raises():
    respx.get("https://careers-nope.icims.com/jobs/search").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        ICIMSSource().fetch("careers-nope", "Nope")


def test_coded_places_and_names():
    assert _place("IN-Hyderabad") == "Hyderabad, India"
    assert _place("Remote") == "Remote"
    assert ICIMSSource().default_name("hubcareers-docusign") == "Docusign"
    assert ICIMSSource().board_candidates("Health Edge") == ["careers-healthedge", "careers-health-edge"]
    assert board_from_url("https://hubcareers-docusign.icims.com/jobs/30406/job") == ("icims", "hubcareers-docusign")
    assert board_from_url("https://careers.icims.com/careers-home/jobs/6503") is None
