from types import SimpleNamespace
from typing import Any

import httpx
import respx

from app.agents.careers_pages.agent import find_careers_page
from app.agents.schemas import Usage


class FakeMessages:
    def __init__(self, urls: list[str]):
        self.urls = urls
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        results = [SimpleNamespace(url=url) for url in self.urls]
        return SimpleNamespace(
            content=[SimpleNamespace(type="web_search_tool_result", content=results)],
            usage=SimpleNamespace(input_tokens=50, output_tokens=5),
        )


def client(urls: list[str]) -> Any:
    return SimpleNamespace(messages=FakeMessages(urls))


@respx.mock
def test_a_suggested_page_that_loads_is_kept_without_searching():
    respx.get("https://www.boeing.com/careers").mock(return_value=httpx.Response(200))
    search = client([])

    url = find_careers_page(search, "claude-haiku-5-5", "Boeing", "https://www.boeing.com/careers", Usage(), httpx.Client())

    assert url == "https://www.boeing.com/careers" and search.messages.calls == []


@respx.mock
def test_a_missing_suggestion_falls_back_to_a_web_search():
    respx.get("https://acme.com/jobs-old").mock(return_value=httpx.Response(404))
    search = client(["https://acme.com/about", "https://acme.com/careers/open-roles"])
    usage = Usage()

    url = find_careers_page(search, "claude-haiku-5-5", "Acme", "https://acme.com/jobs-old", usage, httpx.Client())

    assert url == "https://acme.com/careers/open-roles"
    [call] = search.messages.calls
    assert call["tools"][0]["max_uses"] == 1 and "jobs.lever.co" in call["tools"][0]["blocked_domains"]
    assert usage.input_tokens == 50


def test_no_careers_like_result_means_not_found():
    assert find_careers_page(client(["https://acme.com/about"]), "claude-haiku-5-5", "Acme", None, Usage(), httpx.Client()) is None
