import pytest

from app.sources import board_candidates, display_name, find_company
from app.sources.base import (
    BoardNotFound,
    CompanyNotFound,
    Posting,
    join_locations,
    matches_location,
    matches_workplace,
    workplace_from_location,
)


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


class FakeSource:
    def __init__(self, name: str, boards: dict[str, int]):
        self.name = name
        self.boards = boards
        self.calls: list[str] = []

    def fetch(self, board: str, company: str) -> list[Posting]:
        self.calls.append(board)
        if board not in self.boards:
            raise BoardNotFound(board)
        return [posting(self.name, board)] * self.boards[board]


def test_board_candidates():
    assert board_candidates("Scale AI") == ["scaleai", "scale-ai"]
    assert board_candidates("Stripe") == ["stripe"]
    assert board_candidates("  Acme, Inc. ") == ["acmeinc", "acme-inc"]
    assert board_candidates("!!!") == []


def test_finds_company_on_any_source():
    greenhouse = FakeSource("greenhouse", {})
    ashby = FakeSource("ashby", {"scale-ai": 2})

    postings = find_company("Scale AI", [greenhouse, ashby])

    assert [p.source for p in postings] == ["ashby", "ashby"]
    assert greenhouse.calls == ["scaleai", "scale-ai"]


def test_board_with_most_postings_wins():
    greenhouse = FakeSource("greenhouse", {"acme": 1})
    lever = FakeSource("lever", {"acme": 3})
    ashby = FakeSource("ashby", {"acme": 2})

    postings = find_company("Acme", [greenhouse, lever, ashby])

    assert len(postings) == 3 and postings[0].source == "lever"


def test_empty_board_when_nothing_else_matches():
    assert find_company("Acme", [FakeSource("greenhouse", {"acme": 0})]) == []


def test_unknown_company_raises():
    with pytest.raises(CompanyNotFound, match="Couldn't find job listings for Nowhere"):
        find_company("Nowhere", [FakeSource("greenhouse", {}), FakeSource("lever", {})])


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

    find_company("ramp", [RecordingSource("ashby", {"ramp": 1})])

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


def test_join_locations_and_workplace_from_location():
    assert join_locations("Miami, FL", None, " Miami, FL ", "Austin, TX") == "Miami, FL; Austin, TX"
    assert join_locations(None, "") is None
    assert workplace_from_location("Remote, US") == "remote"
    assert workplace_from_location("Hybrid - NYC") == "hybrid"
    assert workplace_from_location("Dublin") is None
