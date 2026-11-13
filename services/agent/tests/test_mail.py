from types import SimpleNamespace
from typing import Any, cast

import pytest

from app import mail
from app.config import Settings


def settings(**fields: Any) -> Settings:
    defaults = {"resend_api_key": "re_test", "email_from": "Job Scout <onboarding@resend.dev>", "admin_email": "admin@example.com"}
    return cast(Settings, SimpleNamespace(**{**defaults, **fields}))


def capture(monkeypatch: pytest.MonkeyPatch, fail: bool = False) -> list[tuple[Any, Any]]:
    sent: list[tuple[Any, Any]] = []

    def send(params: Any, options: Any = None) -> dict[str, str]:
        if fail:
            raise RuntimeError("rate limited")
        sent.append((params, options))
        return {"id": "email-1"}

    monkeypatch.setattr(mail.resend.Emails, "send", send)
    return sent


def test_an_email_goes_out_through_resend_with_its_idempotency_key(monkeypatch: pytest.MonkeyPatch):
    sent = capture(monkeypatch)

    assert mail.send_email(settings(), "user@example.com", "Hello", "<p>Hi</p>", "welcome/1")

    [(params, options)] = sent
    assert params == {"from": "Job Scout <onboarding@resend.dev>", "to": ["user@example.com"], "subject": "Hello", "html": "<p>Hi</p>"}
    assert options == {"idempotency_key": "welcome/1"}


def test_nothing_is_sent_without_an_api_key(monkeypatch: pytest.MonkeyPatch):
    sent = capture(monkeypatch)

    assert not mail.send_email(settings(resend_api_key=None), "user@example.com", "Hello", "<p>Hi</p>")
    assert sent == []


def test_a_refused_email_is_logged_not_raised(monkeypatch: pytest.MonkeyPatch):
    capture(monkeypatch, fail=True)

    assert not mail.send_email(settings(), "user@example.com", "Hello", "<p>Hi</p>")


def test_an_alert_goes_to_the_admin_with_its_lines_escaped(monkeypatch: pytest.MonkeyPatch):
    sent = capture(monkeypatch)

    assert mail.alert_admin(settings(), "Refresh failed", ["Error: <timeout>", "Second line"])

    [(params, _)] = sent
    assert params["to"] == ["admin@example.com"] and params["subject"] == "[Job Scout] Refresh failed"
    assert params["html"] == "<p>Error: &lt;timeout&gt;</p><p>Second line</p>"


def test_no_alert_without_an_admin_address(monkeypatch: pytest.MonkeyPatch):
    sent = capture(monkeypatch)

    assert not mail.alert_admin(settings(admin_email=None), "Refresh failed", ["Error"])
    assert sent == []
