from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.sources import board_from_url, board_hosts, display_name, find_company, http
from app.sources.base import BoardNotFound, CompanyNotFound, JobSource, Posting, SourceName
from app.sources.filters import matches_exclusions, matches_location, matches_workplace, posted_within
from app.sources.greenhouse import GreenhouseSource
from app.sources.text import join_locations, workplace_from_location


def posting(source: SourceName, board: str) -> Posting:
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
        self.name = name  # pyright: ignore[reportAttributeAccessIssue]
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

    found = find_company("Scale AI", (greenhouse, ashby), cached=False)

    assert (found.source, found.board) == ("ashby", "scale-ai")
    assert [p.source for p in found.postings] == ["ashby", "ashby"]
    assert greenhouse.calls == ["scaleai", "scale-ai"]


def test_board_with_most_postings_wins():
    greenhouse = FakeSource("greenhouse", {"acme": 1})
    lever = FakeSource("lever", {"acme": 3})
    ashby = FakeSource("ashby", {"acme": 2})

    found = find_company("Acme", (greenhouse, lever, ashby), cached=False)

    assert found.source == "lever" and len(found.postings) == 3


def test_a_board_without_postings_still_finds_the_company():
    found = find_company("acme", (FakeSource("greenhouse", {"acme": 0}),), cached=False)

    assert (found.source, found.board, found.name, found.postings) == ("greenhouse", "acme", "Acme", [])


def test_unknown_company_raises():
    with pytest.raises(CompanyNotFound, match="Couldn't find job listings for Nowhere"):
        find_company("Nowhere", (FakeSource("greenhouse", {}), FakeSource("lever", {})), cached=False)


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

    find_company("ramp", (RecordingSource("ashby", {"ramp": 1}),), cached=False)

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
    assert board_from_url("https://jobs.gem.com/silkline/am9icG9zdDrLws") == ("gem", "silkline")
    assert board_from_url("https://ats.rippling.com/etc/jobs/3300a2a6") == ("rippling", "etc")
    assert board_from_url("https://ats.rippling.com/en-ca/flyover-las-vegas/jobs/2a13ee") == ("rippling", "flyover-las-vegas")
    assert board_from_url("https://prophetexchange.pinpointhq.com/en/postings/5d226f78") == ("pinpoint", "prophetexchange")
    assert board_from_url("https://axmed.teamtailor.com/jobs/8175859-ai-engineer") == ("teamtailor", "axmed")
    assert board_from_url("https://jobs.polymer.co/return/41723") == ("polymer", "return")
    assert board_from_url("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/210792038") == (
        "oracle",
        "jpmc.fa/cx_1001",
    )
    assert board_from_url("https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions") == (
        "oracle",
        "eeho.fa.us2/cx_1",
    )


def test_board_from_url_skips_site_pages_and_other_hosts():
    assert board_from_url("https://job-boards.greenhouse.io/job-openings") is None
    assert board_from_url("https://apply.workable.com/j/81B46579FE") is None
    assert board_from_url("https://www.recruitee.com/pricing") is None
    assert board_from_url("https://example.com/acme") is None
    assert board_from_url("https://jobs.lever.co/") is None
    assert board_from_url("https://www.teamtailor.com/en/pricing") is None
    assert board_from_url("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/") is None


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
        "jobs.gem.com",
        "ats.rippling.com",
        "pinpointhq.com",
        "teamtailor.com",
        "jobs.polymer.co",
        "oraclecloud.com",
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
    assert careers_url("gem", "silkline") == "https://jobs.gem.com/silkline"
    assert careers_url("rippling", "etc") == "https://ats.rippling.com/etc/jobs"
    assert careers_url("pinpoint", "prophetexchange") == "https://prophetexchange.pinpointhq.com/"
    assert careers_url("teamtailor", "axmed") == "https://axmed.teamtailor.com/jobs"
    assert careers_url("polymer", "return") == "https://jobs.polymer.co/return"
    assert careers_url("oracle", "jpmc.fa/cx_1001") == "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001"
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
    from app import sources

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


class JsonSource(JobSource):
    name = "greenhouse"
    label = "Json"
    board_hosts = ()

    def fetch(self, board: str, company: str) -> list[Posting]:
        return [posting(self.name, board)] * self._get_json(board, f"https://jobs.example/{board}")["jobs"]


def flaky_board(monkeypatch: pytest.MonkeyPatch, *failures: httpx.Response | Exception) -> tuple[list[float], respx.Route]:
    waits: list[float] = []
    monkeypatch.setattr(http.time, "sleep", waits.append)
    route = respx.get("https://jobs.example/acme").mock(side_effect=[*failures, httpx.Response(200, json={"jobs": 2})])
    return waits, route


@respx.mock
def test_a_rate_limited_request_waits_as_asked_and_is_retried(monkeypatch: pytest.MonkeyPatch):
    waits, route = flaky_board(monkeypatch, httpx.Response(429, headers={"Retry-After": "5"}))

    assert len(JsonSource().fetch("acme", "Acme")) == 2
    assert route.call_count == 2 and waits == [5.0]


@respx.mock
def test_a_server_error_is_retried_after_growing_waits(monkeypatch: pytest.MonkeyPatch):
    waits, route = flaky_board(monkeypatch, httpx.Response(503), httpx.Response(502))

    assert len(JsonSource().fetch("acme", "Acme")) == 2
    assert route.call_count == 3 and waits == list(http.RETRY_WAITS[:2])


@respx.mock
def test_a_dropped_connection_is_retried(monkeypatch: pytest.MonkeyPatch):
    waits, route = flaky_board(monkeypatch, httpx.ConnectError("connection reset"))

    assert len(JsonSource().fetch("acme", "Acme")) == 2
    assert route.call_count == 2 and waits == [http.RETRY_WAITS[0]]


def test_a_job_link_points_to_its_posting_by_link_id_or_the_last_piece_of_a_path_id():
    listed = posting("greenhouse", "acme").model_copy(update={"external_id": "4012", "url": "https://boards.greenhouse.io/acme/jobs/4012?gh_src=x"})
    pathed = posting("workday", "ge.wd5/site").model_copy(update={"external_id": "/job/Evendale/Engineer_R1-2"})
    source = GreenhouseSource()

    assert source.is_job_link(listed, "https://boards.greenhouse.io/acme/jobs/4012")
    assert source.is_job_link(listed, "https://job-boards.greenhouse.io/acme/jobs/4012")
    assert source.is_job_link(pathed, "https://ge.wd5.myworkdayjobs.com/en-US/site/details/Engineer_R1-2")
    assert not source.is_job_link(listed, "https://boards.greenhouse.io/acme/jobs/40123")
