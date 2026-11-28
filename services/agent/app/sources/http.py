"""Sending requests to job systems and Hacker News, retrying failures that tend to pass."""

import time
from collections.abc import Callable

import httpx

# Waits before each retry of a rate limit, a server error or a dropped connection.
RETRY_WAITS = (2.0, 4.0, 8.0)
MAX_RETRY_WAIT = 30.0
RETRIED_STATUSES = frozenset({429, 500, 502, 503, 504})
TIMEOUT_RETRIES = 1


def send(request: Callable[[], httpx.Response]) -> httpx.Response:
    """
    Sends a request, retrying a rate limit, a server error or a dropped
    connection after each of RETRY_WAITS, or the wait a 429 asks for up to
    MAX_RETRY_WAIT, and a timeout TIMEOUT_RETRIES times. Returns the last
    response, or raises the last connection error or timeout.
    """
    timeouts = 0
    for wait in RETRY_WAITS:
        try:
            res = request()
        except httpx.TimeoutException:
            timeouts += 1
            if timeouts > TIMEOUT_RETRIES:
                raise
            time.sleep(wait)
            continue
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            time.sleep(wait)
            continue
        if res.status_code not in RETRIED_STATUSES:
            return res
        time.sleep(min(retry_after(res) or wait, MAX_RETRY_WAIT))
    return request()


def retry_after(res: httpx.Response) -> float | None:
    """The seconds a response asks to wait before retrying, when it says in seconds."""
    value = res.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else None
