import httpx
import pytest
import respx

from app.sources import board_from_url
from app.sources.base import BoardNotFound
from app.sources.jobvite import JobviteSource

LIST = """
<table class="jv-job-list"><tbody>
<tr>
    <td class="jv-job-list-name">
        <a href="/egnyte/job/opPUAfws">FP&amp;A Manager</a>
    </td>
    <td class="jv-job-list-location">
        Mountain View,
        California
    </td>
</tr>
<tr>
    <td class="jv-job-list-name">
        <a href="/egnyte/job/oz90Afw2">Senior Engineer</a>
    </td>
    <td class="jv-job-list-location">
        Remote , 19 Locations
    </td>
</tr>
</tbody></table>"""


@respx.mock
def test_fetch_normalizes_the_job_list():
    respx.get("https://jobs.jobvite.com/egnyte/jobs").mock(return_value=httpx.Response(200, text=LIST))

    office, remote = JobviteSource().fetch("egnyte", "Egnyte")

    assert (office.source, office.board, office.external_id) == ("jobvite", "egnyte", "opPUAfws")
    assert office.title == "FP&A Manager" and office.company == "Egnyte"
    assert office.url == "https://jobs.jobvite.com/egnyte/job/opPUAfws"
    assert office.location == "Mountain View, California" and office.workplace_type is None
    assert remote.location == "Remote , 19 Locations" and remote.workplace_type == "remote"


@respx.mock
def test_describe_reads_the_job_page_json_ld():
    page = '<script type="application/ld+json">{"@type": "JobPosting", "description": "<p>Close the books.</p>"}</script>'
    respx.get("https://jobs.jobvite.com/egnyte/jobs").mock(return_value=httpx.Response(200, text=LIST))
    respx.get("https://jobs.jobvite.com/egnyte/job/opPUAfws").mock(return_value=httpx.Response(200, text=page))
    source = JobviteSource()
    posting = source.fetch("egnyte", "Egnyte")[0]

    assert source.describe(posting) == "Close the books."


@respx.mock
def test_unknown_company_redirect_is_not_found():
    respx.get("https://jobs.jobvite.com/nope/jobs").mock(
        return_value=httpx.Response(302, headers={"location": "http://search.jobvite.com/?invalid=1"})
    )

    with pytest.raises(BoardNotFound):
        JobviteSource().fetch("nope", "Nope")


def test_boards_come_from_job_pages():
    assert board_from_url("https://jobs.jobvite.com/ninjaone/job/oUarAfwP") == ("jobvite", "ninjaone")
    assert JobviteSource().careers_url("egnyte") == "https://jobs.jobvite.com/egnyte/jobs"
