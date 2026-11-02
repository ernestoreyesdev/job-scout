import httpx
import pytest
import respx

from app.sources import board_from_url
from app.sources.base import BoardNotFound
from app.sources.personio import PersonioSource

FEED = "https://gokarla-gmbh.jobs.personio.de/xml"


def position(id: str, office: str, descriptions: str = "", extra: str = "") -> str:
    return f"""
    <position>
        <id>{id}</id>
        <office>{office}</office>
        {extra}
        <name>Senior Software Engineer {id}</name>
        <jobDescriptions>{descriptions}</jobDescriptions>
        <createdAt>2026-02-02T13:44:56+00:00</createdAt>
    </position>"""


SECTION = "<jobDescription><name>About the Role</name><value><![CDATA[<p>Build agents.</p>]]></value></jobDescription>"
GERMAN = "<jobDescription><name>Deine Aufgaben</name><value><![CDATA[<p>Agenten bauen.</p>]]></value></jobDescription>"


def feed(*positions: str) -> httpx.Response:
    return httpx.Response(200, text=f'<?xml version="1.0" encoding="UTF-8"?><workzag-jobs>{"".join(positions)}</workzag-jobs>')


@respx.mock
def test_fetch_normalizes_positions():
    extra = "<additionalOffices><office>Berlin</office><office>Munich</office></additionalOffices>"
    respx.get(FEED, params={"language": "en"}).mock(return_value=feed(position("2515695", "Berlin/Remote", SECTION, extra)))

    [posting] = PersonioSource().fetch("gokarla-gmbh", "GoKarla")

    assert (posting.source, posting.board, posting.external_id) == ("personio", "gokarla-gmbh", "2515695")
    assert posting.company == "GoKarla" and posting.title == "Senior Software Engineer 2515695"
    assert posting.url == "https://gokarla-gmbh.jobs.personio.de/job/2515695"
    assert posting.location == "Berlin/Remote; Berlin; Munich"
    assert posting.description == "About the Role\nBuild agents."
    assert posting.posted_at.isoformat() == "2026-02-02T13:44:56+00:00"
    assert posting.workplace_type == "remote"


@respx.mock
def test_jobs_written_in_another_language_take_the_default_feed():
    english = respx.get(FEED, params={"language": "en"}).mock(
        return_value=feed(position("1", "Berlin", SECTION), position("2", "Augsburg"))
    )
    default = respx.get(FEED, params={}).mock(return_value=feed(position("1", "Berlin"), position("2", "Augsburg", GERMAN)))

    first, second = PersonioSource().fetch("gokarla-gmbh", "GoKarla")

    assert english.called and default.called
    assert first.description == "About the Role\nBuild agents."
    assert second.description == "Deine Aufgaben\nAgenten bauen."


@respx.mock
def test_unknown_board_raises():
    respx.get("https://nope.jobs.personio.de/xml").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        PersonioSource().fetch("nope", "Nope")


@pytest.mark.parametrize(
    "url", ["https://arconsis.jobs.personio.com/?language=de", "https://arconsis.jobs.personio.de/job/2868471"]
)
def test_boards_come_from_either_job_page_host(url: str):
    assert board_from_url(url) == ("personio", "arconsis")
