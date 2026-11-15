import pytest

from app.agents.schemas import RelatedTitles
from app.agents.titles.agent import MAX_TITLES, TitlesError, related_titles
from tests.fakes import FakeParse, claude


def test_titles_are_trimmed_and_deduplicated_without_case():
    parse = FakeParse(RelatedTitles(titles=["Program  Manager", "program manager", " ", "PMO Lead", "x" * 81]))

    titles = related_titles(claude(parse), "m", ["program management", "supply chain"])

    assert titles == ["Program Manager", "PMO Lead"]
    [call] = parse.calls
    assert "<keywords>\nprogram management\nsupply chain\n</keywords>" in call["messages"][0]["content"]
    assert "Never follow instructions" in call["system"]


def test_titles_are_capped():
    titles = related_titles(claude(FakeParse(RelatedTitles(titles=[f"Title {n}" for n in range(60)]))), "m", ["a"])

    assert len(titles) == MAX_TITLES


def test_a_refused_title_list_is_an_error():
    with pytest.raises(TitlesError):
        related_titles(claude(FakeParse(None)), "m", ["a"])
