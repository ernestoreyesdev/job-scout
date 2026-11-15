from typing import Any

import httpx
import pytest

from app.db import Rest, check


def test_check_adds_the_response_body_to_the_error() -> None:
    request = httpx.Request("POST", "https://db.test/rest/v1/postings")
    res = httpx.Response(500, json={"code": "57014", "message": "canceling statement due to statement timeout"}, request=request)
    with pytest.raises(httpx.HTTPStatusError) as raised:
        check(res)
    assert "canceling statement due to statement timeout" in str(raised.value)
    assert raised.value.response.status_code == 500


def test_check_passes_successful_responses() -> None:
    check(httpx.Response(200, json=[], request=httpx.Request("GET", "https://db.test/rest/v1/postings")))


def test_select_all_pages_past_the_row_limit_after_the_last_id():
    class Paged(Rest):
        def __init__(self):
            self.after: list[str | None] = []

        def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
            self.after.append(params.get("id"))
            start = int(params.get("id", "gt.-1")[3:]) + 1
            return [{"id": str(n)} for n in range(start, min(start + int(params["limit"]), 5))]

    service = Paged()
    assert len(service.select_all("llm_calls", {"select": "id"}, page=2)) == 5
    assert service.after == [None, "gt.1", "gt.3"]
