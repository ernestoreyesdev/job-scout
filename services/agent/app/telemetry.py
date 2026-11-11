import hashlib
import json
import logging
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.agents.discovery.prompts import DISCOVERY_SYSTEM, NAMING_SYSTEM
from app.agents.follow_up.prompts import FOLLOW_UP_SYSTEM
from app.agents.gap_analysis.prompts import GAP_SYSTEM
from app.agents.hiring_threads.prompts import EXTRACTION_SYSTEM
from app.agents.scoring.prompts import FIT_SYSTEM
from app.agents.titles.prompts import TITLES_SYSTEM
from app.agents.triage.prompts import TRIAGE_SYSTEM
from app.db import Rest

logger = logging.getLogger("agent")

# The run the current code is working on; worker threads see it through ContextThreadPool.
current_run: ContextVar[str | None] = ContextVar("current_run", default=None)

# Each agent's fixed system prompt names the step that made the call, even from a worker thread.
STEPS = {
    FIT_SYSTEM: "scoring",
    TRIAGE_SYSTEM: "shortlist",
    TITLES_SYSTEM: "titles",
    DISCOVERY_SYSTEM: "discovery",
    NAMING_SYSTEM: "naming",
    EXTRACTION_SYSTEM: "hacker_news",
    GAP_SYSTEM: "gap_analysis",
    FOLLOW_UP_SYSTEM: "follow_up",
}
MAX_ERROR_LENGTH = 500


class CallLog:
    """Claude calls made for one user, and run when there is one, kept in memory until save()."""

    def __init__(self, user_id: str, run_id: str | None = None):
        self.user_id = user_id
        self.run_id = run_id
        self.rows: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def add(self, kwargs: dict[str, Any], response: Any, started: float, error: Exception | None) -> None:
        usage = getattr(response, "usage", None)
        server_tools = getattr(usage, "server_tool_use", None)
        row = {
            "run_id": self.run_id,
            "user_id": self.user_id,
            "step": STEPS.get(str(kwargs.get("system")), "other"),
            "model": str(kwargs.get("model", "")),
            "prompt_version": prompt_version(kwargs.get("system"), kwargs.get("output_format")),
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "web_search_requests": getattr(server_tools, "web_search_requests", 0) or 0,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "stop_reason": getattr(response, "stop_reason", None),
            "error": (str(error) or error.__class__.__name__)[:MAX_ERROR_LENGTH] if error else None,
        }
        with self._lock:
            self.rows.append(row)

    def save(self, service: Rest) -> None:
        """Writes the recorded calls in one insert; a failure is logged so it never fails the run."""
        with self._lock:
            rows, self.rows = self.rows, []
        if not rows:
            return
        try:
            service.insert("llm_calls", rows)
        except Exception as error:
            logger.warning("saving %d Claude calls failed: %s", len(rows), error)


class RecordingClient:
    """An Anthropic client whose messages.create and beta.messages.parse calls are recorded in a CallLog."""

    def __init__(self, client: Any, log: CallLog):
        self._client = client
        self._log = log

    @property
    def models(self) -> Any:
        return self._client.models

    @property
    def messages(self) -> "_RecordedMessages":
        return _RecordedMessages(self._client.messages, self._log)

    @property
    def beta(self) -> SimpleNamespace:
        return SimpleNamespace(messages=_RecordedMessages(self._client.beta.messages, self._log))


class _RecordedMessages:
    def __init__(self, messages: Any, log: CallLog):
        self._messages = messages
        self._log = log

    def create(self, **kwargs: Any) -> Any:
        return self._call(self._messages.create, kwargs)

    def parse(self, **kwargs: Any) -> Any:
        return self._call(self._messages.parse, kwargs)

    def _call(self, method: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
        started = time.monotonic()
        try:
            response = method(**kwargs)
        except Exception as error:
            self._log.add(kwargs, None, started, error)
            raise
        self._log.add(kwargs, response, started, None)
        return response


@contextmanager
def timed(timings: dict[str, int] | None, step: str) -> Iterator[None]:
    """Adds the block's milliseconds to timings[step]; does nothing without timings."""
    started = time.monotonic()
    try:
        yield
    finally:
        if timings is not None:
            timings[step] = timings.get(step, 0) + round((time.monotonic() - started) * 1000)


class ContextThreadPool(ThreadPoolExecutor):
    """A thread pool whose tasks run with the submitting thread's context, so logs keep the current run."""

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
        return super().submit(copy_context().run, fn, *args, **kwargs)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, message, the current run, any extra fields and the traceback."""

    _standard = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "run_id": current_run.get(),
        }
        line.update({key: value for key, value in record.__dict__.items() if key not in self._standard})
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging() -> None:
    """Sends the agent's logs to stdout as JSON lines from INFO up; safe to call more than once."""
    if any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def prompt_version(system: Any, output_format: Any = None) -> str | None:
    """
    The first 8 hex digits of a hash of a call's system prompt and, when there
    is one, its structured output schema; changing either changes the version.
    """
    if not system:
        return None
    schema = output_format.model_json_schema() if hasattr(output_format, "model_json_schema") else None
    text = json.dumps([system, schema], sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:8]
