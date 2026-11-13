from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.config import Settings
from scripts import refresh_boards as refresh


def fake_settings(**fields: Any) -> Settings:
    return cast(Settings, SimpleNamespace(**fields))


def capture_alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str], str | None]]:
    alerts: list[tuple[str, list[str], str | None]] = []
    monkeypatch.setattr(refresh, "service_db", lambda settings: None)
    monkeypatch.setattr(
        refresh, "alert_admin", lambda settings, subject, lines, key=None: alerts.append((subject, lines, key)) or True
    )
    return alerts


def test_a_failed_refresh_emails_the_admin_once_a_day(monkeypatch: pytest.MonkeyPatch):
    alerts = capture_alerts(monkeypatch)

    def fail(service: Any) -> dict[str, Any]:
        raise RuntimeError("database down")

    monkeypatch.setattr(refresh, "refresh_boards", fail)

    refresh.run_refresh(fake_settings())

    [(subject, lines, key)] = alerts
    assert subject == "Board refresh failed" and "database down" in lines[0]
    assert key and key.startswith("refresh-failed/")


def test_a_refresh_that_misses_boards_names_them_and_a_clean_one_sends_nothing(monkeypatch: pytest.MonkeyPatch):
    alerts = capture_alerts(monkeypatch)
    fetches = [{"board": "lever/b", "outcome": "unreachable"}, {"board": "ashby/a", "outcome": "ok"}]
    monkeypatch.setattr(refresh, "refresh_boards", lambda service: {"jobs": 10, "boards": 1, "board_fetches": fetches})

    refresh.run_refresh(fake_settings())

    [(subject, lines, _)] = alerts
    assert subject == "Board refresh couldn't reach 1 board" and "lever/b" in lines

    alerts.clear()
    monkeypatch.setattr(refresh, "refresh_boards", lambda service: {"jobs": 10, "boards": 1, "board_fetches": fetches[1:]})
    refresh.run_refresh(fake_settings())
    assert alerts == []
