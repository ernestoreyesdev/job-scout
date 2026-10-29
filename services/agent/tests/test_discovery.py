from types import SimpleNamespace
from typing import Any

from app.agents.discovery.agent import FoundBoard, discover_boards, name_companies
from app.agents.schemas import CompanyName, CompanyNames, Usage
from app.sources import board_hosts


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
    usage = Usage()

    boards = discover_boards(
        SimpleNamespace(messages=messages), "claude-haiku-5-5", ["software engineer"], ["remote"], "Florida", usage
    )

    assert [(b.source, b.board) for b in boards] == [("lever", "palantir"), ("ashby", "notion")]
    assert boards[0].titles == ["Jobs: https://jobs.lever.co/palantir/1", "Jobs: https://jobs.lever.co/palantir"]
    assert (usage.input_tokens, usage.web_search_requests) == (500, 2)
    [call] = messages.calls
    [tool] = call["tools"]
    assert tool["allowed_domains"] == board_hosts() and tool["max_uses"] == 3
    prompt = call["messages"][0]["content"]
    assert '"software engineer"' in prompt and "remote" in prompt and "Florida" in prompt


class FakeParse:
    def __init__(self, names: list[tuple[str, str]]):
        self.names = names
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        companies = [CompanyName(board=board, name=name, kind=kind) for board, name, kind in self.names]
        return SimpleNamespace(parsed_output=CompanyNames(companies=companies), usage=SimpleNamespace(input_tokens=80))


def test_name_companies_maps_names_back_to_boards():
    parse = FakeParse(
        [
            ("workday/cvshealth.wd1/careers", " CVS Health ", "employer"),
            ("lever/made-up", "Nobody", "employer"),
            ("lever/acme", "", "staffing"),
        ]
    )
    boards = [FoundBoard("workday", "cvshealth.wd1/careers", ["Pharmacy jobs at CVS Health"]), FoundBoard("lever", "acme")]
    usage = Usage()

    names = name_companies(SimpleNamespace(beta=SimpleNamespace(messages=parse)), "claude-haiku-5-5", boards, usage)

    assert {key: (entry.name, entry.kind) for key, entry in names.items()} == {
        ("workday", "cvshealth.wd1/careers"): ("CVS Health", "employer")
    }
    assert usage.input_tokens == 80
    [call] = parse.calls
    prompt = call["messages"][0]["content"]
    assert "board: workday/cvshealth.wd1/careers" in prompt and "Pharmacy jobs at CVS Health" in prompt
    assert "page titles: none" in prompt and call["output_format"] is CompanyNames


def test_name_companies_makes_no_call_without_boards():
    parse = FakeParse([])

    assert name_companies(SimpleNamespace(beta=SimpleNamespace(messages=parse)), "m", [], Usage()) == {}
    assert parse.calls == []
