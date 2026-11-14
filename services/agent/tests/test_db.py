import httpx
import pytest

from app.db import check


def test_check_adds_the_response_body_to_the_error() -> None:
    request = httpx.Request("POST", "https://db.test/rest/v1/postings")
    res = httpx.Response(500, json={"code": "57014", "message": "canceling statement due to statement timeout"}, request=request)
    with pytest.raises(httpx.HTTPStatusError) as raised:
        check(res)
    assert "canceling statement due to statement timeout" in str(raised.value)
    assert raised.value.response.status_code == 500


def test_check_passes_successful_responses() -> None:
    check(httpx.Response(200, json=[], request=httpx.Request("GET", "https://db.test/rest/v1/postings")))
