from datetime import UTC, datetime

import pytest

from app.sources import board_from_url, board_hosts, display_name, find_company
from app.sources.base import BoardNotFound, CompanyNotFound, JobSource, Posting
from app.sources.filters import matches_exclusions, matches_location, matches_workplace, posted_within
from app.sources.greenhouse import GreenhouseSource
from app.sources.text import join_locations, workplace_from_location


def posting(source: str, board: str) -> Posting:
    return Posting(
        source=source,
        board=board,
        external_id=f"{source}-{board}",
        title="Engineer",
        company="Acme",
        location=None,
        url="https://example.com",
        description="",
        posted_at=None,
    )


class FakeSource(JobSource):
    label = "Fake"
    board_hosts = ()

    def __init__(self, name: str, boards: dict[str, int]):
        super().__init__()
        self.name = name
        self.boards = boards
        self.calls: list[str] = []

    def fetch(self, board: str, company: str) -> list[Posting]:
        self.calls.append(board)
        if board not in self.boards:
            raise BoardNotFound(board)
        return [posting(self.name, board)] * self.boards[board]


def test_board_candidates():
    source = GreenhouseSource()
    assert source.board_candidates("Scale AI") == ["scaleai", "scale-ai"]
    assert source.board_candidates("Stripe") == ["stripe"]
    assert source.board_candidates("  Acme, Inc. ") == ["acmeinc", "acme-inc"]
    assert source.board_candidates("!!!") == []


def test_finds_company_on_any_source():
    greenhouse = FakeSource("greenhouse", {})
    ashby = FakeSource("ashby", {"scale-ai": 2})

    found = find_company("Scale AI", (greenhouse, ashby))

    assert (found.source, found.board) == ("ashby", "scale-ai")
    assert [p.source for p in found.postings] == ["ashby", "ashby"]
    assert greenhouse.calls == ["scaleai", "scale-ai"]


def test_board_with_most_postings_wins():
    greenhouse = FakeSource("greenhouse", {"acme": 1})
    lever = FakeSource("lever", {"acme": 3})
    ashby = FakeSource("ashby", {"acme": 2})

    found = find_company("Acme", (greenhouse, lever, ashby))

    assert found.source == "lever" and len(found.postings) == 3


def test_a_board_without_postings_still_finds_the_company():
    found = find_company("acme", (FakeSource("greenhouse", {"acme": 0}),))

    assert (found.source, found.board, found.name, found.postings) == ("greenhouse", "acme", "Acme", [])


def test_unknown_company_raises():
    with pytest.raises(CompanyNotFound, match="Couldn't find job listings for Nowhere"):
        find_company("Nowhere", (FakeSource("greenhouse", {}), FakeSource("lever", {})))


def test_display_name_capitalizes_lowercase_names_only():
    assert display_name("ramp") == "Ramp"
    assert display_name("  scale   ai ") == "Scale Ai"
    assert display_name("OpenAI") == "OpenAI"
    assert display_name("Scale AI") == "Scale AI"


def test_postings_use_the_display_name():
    seen: list[str] = []

    class RecordingSource(FakeSource):
        def fetch(self, board: str, company: str) -> list[Posting]:
            seen.append(company)
            return super().fetch(board, company)

    find_company("ramp", (RecordingSource("ashby", {"ramp": 1}),))

    assert seen == ["Ramp"]


def located(location: str | None, workplace_type: str | None = None) -> Posting:
    return posting("ashby", "acme").model_copy(update={"location": location, "workplace_type": workplace_type})


def test_workplace_filter():
    assert matches_workplace(located("Miami", "hybrid"), [])
    assert matches_workplace(located("Miami", "hybrid"), ["hybrid", "remote"])
    assert not matches_workplace(located("Miami", "onsite"), ["remote"])
    assert matches_workplace(located("Miami"), ["onsite"])
    assert not matches_workplace(located("Miami"), ["remote"])


def test_location_filter_matches_cities_and_states_both_ways():
    assert matches_location(located("Miami, FL", "onsite"), "Florida")
    assert matches_location(located("Tampa, Florida"), "fl")
    assert matches_location(located("San Francisco; New York, New York"), "new york")
    assert not matches_location(located("Chicago, IL", "onsite"), "California")
    assert not matches_location(located("Chicago, IL"), "CA")
    assert not matches_location(located(None), "Miami")


def test_remote_jobs_match_when_open_to_the_us():
    for open_to_us in ["Remote - US", "US", "Remote", None, "United States; Canada", "Remote - FL", "Austin, Texas"]:
        assert matches_location(located(open_to_us, "remote"), "Tampa"), open_to_us
    for abroad in ["France", "Remote - UK", "Brazil", "Remote in Germany", "Latin America"]:
        assert not matches_location(located(abroad, "remote"), "Tampa"), abroad
    assert matches_location(located("Miami, FL"), None)


def test_without_a_location_remote_jobs_must_still_be_open_to_the_us():
    assert matches_location(located("Remote - USA", "remote"), None)
    assert matches_location(located("United States; Ontario", "remote"), None)
    for abroad in ["Remote Spain", "Canada", "Brazil"]:
        assert not matches_location(located(abroad, "remote"), None), abroad
    assert not matches_location(located("Dublin"), None)


def test_join_locations_and_workplace_from_location():
    assert join_locations("Miami, FL", None, " Miami, FL ", "Austin, TX") == "Miami, FL; Austin, TX"
    assert join_locations(None, "") is None
    assert workplace_from_location("Remote, US") == "remote"
    assert workplace_from_location("Hybrid - NYC") == "hybrid"
    assert workplace_from_location("Dublin") is None


def test_board_from_url_covers_every_system():
    assert board_from_url("https://job-boards.greenhouse.io/gusto/jobs/123") == ("greenhouse", "gusto")
    assert board_from_url("https://boards.greenhouse.io/energyhub/jobs/7849949002") == ("greenhouse", "energyhub")
    assert board_from_url("https://jobs.lever.co/palantir") == ("lever", "palantir")
    assert board_from_url("https://jobs.ashbyhq.com/Notion/e327/application") == ("ashby", "notion")
    assert board_from_url("https://jobs.smartrecruiters.com/BoschGroup/744000158566919") == ("smartrecruiters", "boschgroup")
    assert board_from_url("https://apply.workable.com/huggingface/j/81B46579FE/") == ("workable", "huggingface")
    assert board_from_url("https://bunq.recruitee.com/o/data-scientist") == ("recruitee", "bunq")
    assert board_from_url("https://arconsis.jobs.personio.de/job/2868471") == ("personio", "arconsis")
    assert board_from_url("https://hubstaff.bamboohr.com/careers/21") == ("bamboohr", "hubstaff")
    assert board_from_url("https://careers-gdms.icims.com/jobs/76097/role/job") == ("icims", "careers-gdms")
    assert board_from_url("https://jobs.jobvite.com/egnyte/job/opPUAfws") == ("jobvite", "egnyte")


def test_board_from_url_skips_site_pages_and_other_hosts():
    assert board_from_url("https://job-boards.greenhouse.io/job-openings") is None
    assert board_from_url("https://apply.workable.com/j/81B46579FE") is None
    assert board_from_url("https://www.recruitee.com/pricing") is None
    assert board_from_url("https://example.com/acme") is None
    assert board_from_url("https://jobs.lever.co/") is None


def test_board_hosts_lists_every_system():
    assert set(board_hosts()) >= {
        "boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com",
        "jobs.smartrecruiters.com",
        "apply.workable.com",
        "recruitee.com",
        "jobs.personio.de",
        "jobs.personio.com",
        "bamboohr.com",
        "icims.com",
        "jobs.jobvite.com",
    }


def test_careers_urls_for_every_system():
    from app.sources import careers_url

    assert careers_url("greenhouse", "affirm") == "https://job-boards.greenhouse.io/affirm"
    assert careers_url("lever", "aledade") == "https://jobs.lever.co/aledade"
    assert careers_url("ashby", "quora") == "https://jobs.ashbyhq.com/quora"
    assert careers_url("smartrecruiters", "boschgroup") == "https://jobs.smartrecruiters.com/boschgroup"
    assert careers_url("workable", "huggingface") == "https://apply.workable.com/huggingface"
    assert careers_url("recruitee", "bunq") == "https://bunq.recruitee.com/"
    assert careers_url("personio", "arconsis") == "https://arconsis.jobs.personio.de/"
    assert careers_url("bamboohr", "hubstaff") == "https://hubstaff.bamboohr.com/careers"
    assert careers_url("icims", "careers-gdms") == "https://careers-gdms.icims.com/jobs/search?ss=1"
    assert careers_url("jobvite", "egnyte") == "https://jobs.jobvite.com/egnyte/jobs"
    assert careers_url("workday", "nvidia.wd5/nvidiaexternalcareersite") == (
        "https://nvidia.wd5.myworkdayjobs.com/nvidiaexternalcareersite"
    )


def titled(title: str, posted_at: datetime | None = None) -> Posting:
    return posting("ashby", "acme").model_copy(update={"title": title, "posted_at": posted_at})


def test_exclusions_drop_titles_with_any_excluded_word():
    assert matches_exclusions(titled("Senior Software Engineer"), [])
    assert not matches_exclusions(titled("Engineering Manager, Platform"), ["intern", "manager"])
    assert not matches_exclusions(titled("Software Engineering Interns"), ["intern"])
    assert matches_exclusions(titled("Internal Tools Engineer"), ["intern"])


def test_posted_within_keeps_recent_and_undated_jobs():
    now = datetime(2026, 10, 29, tzinfo=UTC)

    assert posted_within(titled("A", datetime(2026, 10, 25, tzinfo=UTC)), 7, now)
    assert not posted_within(titled("A", datetime(2026, 10, 1, tzinfo=UTC)), 7, now)
    assert posted_within(titled("A"), 1, now)
    assert posted_within(titled("A", datetime(2020, 1, 1, tzinfo=UTC)), None, now)


def test_without_a_location_other_jobs_must_be_in_the_us():
    for here in ["San Jose, California, US", "New York, NY (HQ)", "Austin, TX", "San Francisco", "San Francisco; London", "USA-GA-Atlanta", "Dublin, CA", "Paris, TX", None]:
        assert matches_location(located(here, "onsite"), None), here
    for abroad in ["Bangalore, India", "Krakow Poland and 1 more", "Tienen, BE", "London", "Toronto, ON", "Paris", "Bratislava, Slovakia"]:
        assert not matches_location(located(abroad, "hybrid"), None), abroad
    assert matches_location(located("Dublin", "onsite"), "Dublin")


def test_board_fetches_are_reused_until_they_expire(monkeypatch: pytest.MonkeyPatch):
    import app.sources as sources

    source = FakeSource("ashby", {"acme": 2})
    clock = [1000.0]
    monkeypatch.setattr(sources.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(sources, "_board_cache", {})

    first = sources.cached_fetch(source, "acme", "Acme")
    clock[0] += sources.CACHE_SECONDS - 1
    again = sources.cached_fetch(source, "acme", "Acme")
    clock[0] += 2
    sources.cached_fetch(source, "acme", "Acme")

    assert again is first and source.calls == ["acme", "acme"]
    with pytest.raises(BoardNotFound):
        sources.cached_fetch(source, "nope", "Nope")
    assert ("ashby", "nope") not in sources._board_cache
