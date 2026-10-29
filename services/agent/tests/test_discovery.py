from types import SimpleNamespace
from typing import Any

from app.agents.discovery.agent import BOARD_HOSTS, board_from_url, discover_boards
from app.agents.schemas import Usage


def test_board_from_url():
    assert board_from_url("https://job-boards.greenhouse.io/gusto/jobs/123") == ("greenhouse", "gusto")
    assert board_from_url("https://boards.greenhouse.io/energyhub/jobs/7849949002") == ("greenhouse", "energyhub")
    assert board_from_url("https://jobs.lever.co/palantir") == ("lever", "palantir")
    assert board_from_url("https://jobs.ashbyhq.com/Notion/e327/application") == ("ashby", "notion")
    assert board_from_url("https://job-boards.greenhouse.io/job-openings") is None
    assert board_from_url("https://example.com/acme") is None
    assert board_from_url("https://jobs.lever.co/") is None


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
        type="web_search_tool_result", content=[SimpleNamespace(type="web_search_result", url=url) for url in urls]
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

    assert boards == [("lever", "palantir"), ("ashby", "notion")]
    assert (usage.input_tokens, usage.web_search_requests) == (500, 2)
    [call] = messages.calls
    [tool] = call["tools"]
    assert tool["allowed_domains"] == list(BOARD_HOSTS) and tool["max_uses"] == 3
    prompt = call["messages"][0]["content"]
    assert '"software engineer"' in prompt and "remote" in prompt and "Florida" in prompt
