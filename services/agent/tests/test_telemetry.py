from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.schemas import FitScore, RelatedTitles
from app.agents.scoring.prompts import FIT_SYSTEM
from app.agents.titles.prompts import TITLES_SYSTEM
from app.db import Rest
from app.telemetry import CallLog, RecordingClient, prompt_version, timed


class Messages:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("overloaded")
        usage = SimpleNamespace(input_tokens=900, output_tokens=40, cache_read_input_tokens=800, cache_creation_input_tokens=0)
        return SimpleNamespace(usage=usage, stop_reason="end_turn")

    create = parse


class Insert(Rest):
    def __init__(self):
        self.rows: list[Any] = []

    def insert(self, table: str, rows: Any, on_conflict: str | None = None, select: str | None = None) -> list[Any]:
        self.rows.append((table, rows))
        return rows


def client(fail: bool = False) -> SimpleNamespace:
    return SimpleNamespace(messages=Messages(fail), beta=SimpleNamespace(messages=Messages(fail)), models=None)


def test_calls_are_recorded_with_their_step_tokens_and_run():
    log = CallLog("run-1")
    recording = RecordingClient(client(), log)

    recording.beta.messages.parse(model="claude-haiku-5-5", system=FIT_SYSTEM, messages=[])
    recording.messages.create(model="claude-haiku-5-5", system="Something else", messages=[])

    scoring, other = log.rows
    assert (scoring["step"], scoring["run_id"], "user_id" in scoring) == ("scoring", "run-1", False)
    assert (scoring["input_tokens"], scoring["cache_read_input_tokens"], scoring["stop_reason"]) == (900, 800, "end_turn")
    assert scoring["duration_ms"] >= 0 and scoring["error"] is None
    assert other["step"] == "other"


def test_a_failed_call_is_recorded_and_still_raises():
    log = CallLog()
    with pytest.raises(RuntimeError):
        RecordingClient(client(fail=True), log).beta.messages.parse(model="m", system=TITLES_SYSTEM, messages=[])

    [row] = log.rows
    assert (row["step"], row["error"], row["input_tokens"], row["run_id"]) == ("titles", "overloaded", 0, None)


def test_saving_writes_every_call_once():
    log, service = CallLog("run-1"), Insert()
    RecordingClient(client(), log).beta.messages.parse(model="m", system=FIT_SYSTEM, messages=[])

    log.save(service)
    log.save(service)

    [(table, rows)] = service.rows
    assert table == "llm_calls" and len(rows) == 1


def test_timed_adds_up_each_steps_milliseconds():
    timings: dict[str, int] = {}
    with timed(timings, "scoring"):
        pass
    with timed(timings, "scoring"):
        pass
    with timed(None, "titles"):
        pass

    assert list(timings) == ["scoring"] and timings["scoring"] >= 0


def test_log_lines_are_json_with_the_current_run_even_from_a_worker_thread():
    import json
    import logging

    from app.telemetry import ContextThreadPool, JsonFormatter, current_run

    lines: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = Capture()
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("telemetry-test")
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    def work() -> None:
        current_run.set("run-7")
        with ContextThreadPool(max_workers=2) as pool:
            pool.submit(lambda: log.warning("fetching %s failed", "ashby/acme", extra={"board": "ashby/acme"})).result()

    from contextvars import copy_context

    copy_context().run(work)

    [line] = [json.loads(line) for line in lines]
    assert (line["run_id"], line["level"], line["message"], line["board"]) == ("run-7", "warning", "fetching ashby/acme failed", "ashby/acme")
    assert line["time"].endswith("+00:00")


def test_a_prompt_version_changes_with_the_prompt_or_its_output_schema():
    version = prompt_version(FIT_SYSTEM, FitScore)

    assert version == prompt_version(FIT_SYSTEM, FitScore) and len(version or "") == 8
    assert version != prompt_version(FIT_SYSTEM + " ", FitScore)
    assert version != prompt_version(FIT_SYSTEM, RelatedTitles)
    assert prompt_version(None) is None


def test_calls_are_recorded_with_their_prompt_version():
    log = CallLog("run-1")
    RecordingClient(client(), log).beta.messages.parse(model="m", system=FIT_SYSTEM, output_format=FitScore, messages=[])

    [row] = log.rows
    assert row["prompt_version"] == prompt_version(FIT_SYSTEM, FitScore)
