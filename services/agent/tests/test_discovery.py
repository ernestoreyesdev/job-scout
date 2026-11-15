from types import SimpleNamespace
from typing import Any

from app.agents.discovery.agent import FoundBoard, discover_boards, name_companies
from app.agents.schemas import CompanyName, CompanyNames
from app.sources import board_hosts
from tests.fakes import FakeParse, claude


class FakeMessages:
    def __init__(self, content: list[SimpleNamespace]):
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        usage = SimpleNamespace(input_tokens=500, output_tokens=40, server_tool_use=SimpleNamespace(web_search_requests=2))
        return SimpleNamespace(content=self.content, usage=usage)


def results(*urls: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="web_search_tool_result", content=[SimpleNamespace(type="web_search_result", url=url, title=f"Jobs: {url}") for url in urls]
    )


def test_boards_come_from_search_result_urls_in_order_without_duplicates():
    messages = FakeMessages(
        [
            SimpleNamespace(type="server_tool_use"),
            results("https://jobs.lever.co/palantir/1", "https://example.com/x", "https://jobs.ashbyhq.com/notion"),
            SimpleNamespace(type="web_search_tool_result", content=SimpleNamespace(type="web_search_tool_result_error")),
            results("https://jobs.lever.co/palantir"),
            SimpleNamespace(type="text", text="https://jobs.lever.co/fromthereply done"),
        ]
    )
    boards = discover_boards(SimpleNamespace(messages=messages), "claude-haiku-5-5", ["software engineer"], ["remote"], "Florida")

    assert [(b.source, b.board) for b in boards] == [("lever", "palantir"), ("ashby", "notion")]
    assert boards[0].titles == ["Jobs: https://jobs.lever.co/palantir/1", "Jobs: https://jobs.lever.co/palantir"]
    [call] = messages.calls
    [tool] = call["tools"]
    assert tool["allowed_domains"] == board_hosts() and tool["max_uses"] == 3
    prompt = call["messages"][0]["content"]
    assert '"software engineer"' in prompt and "remote" in prompt and "Florida" in prompt


def test_name_companies_maps_names_back_to_boards():
    parse = FakeParse(
        CompanyNames(
            companies=[
                CompanyName(board="workday/cvshealth.wd1/careers", name=" CVS Health ", kind="employer"),
                CompanyName(board="lever/made-up", name="Nobody", kind="employer"),
                CompanyName(board="lever/acme", name="", kind="staffing"),
            ]
        )
    )
    boards = [FoundBoard("workday", "cvshealth.wd1/careers", ["Pharmacy jobs at CVS Health"]), FoundBoard("lever", "acme")]
    names = name_companies(claude(parse), "claude-haiku-5-5", boards)

    assert {key: (entry.name, entry.kind) for key, entry in names.items()} == {
        ("workday", "cvshealth.wd1/careers"): ("CVS Health", "employer")
    }
    [call] = parse.calls
    prompt = call["messages"][0]["content"]
    assert "board: workday/cvshealth.wd1/careers" in prompt and "Pharmacy jobs at CVS Health" in prompt
    assert "page titles: none" in prompt and call["output_format"] is CompanyNames


def test_name_companies_makes_no_call_without_boards():
    parse = FakeParse(CompanyNames(companies=[]))

    assert name_companies(claude(parse), "m", []) == {}
    assert parse.calls == []
