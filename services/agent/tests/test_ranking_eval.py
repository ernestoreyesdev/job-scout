import threading
from typing import Any

import pytest

from app.sources.base import Posting
from evals.ranking import run
from tests.test_orchestrator import SETTINGS, posting


def test_the_title_shortlist_runs_in_batches(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(run, "MAX_CANDIDATES", 3)
    fresh = [(f"posting-{n}", posting(str(n), f"Software Engineer {n}")) for n in range(1, 8)]
    calls: list[list[str]] = []
    lock = threading.Lock()

    def triage(client: Any, model: str, resume_text: str, postings: list[Posting], count: int) -> list[int]:
        with lock:
            calls.append([p.external_id for p in postings])
        return [len(postings) - 1]

    picked = run.by_title_fit(fresh, 1, None, SETTINGS, "Python developer.", triage)

    batches, final = sorted(calls[:-1]), calls[-1]
    assert batches == [["1", "2", "3"], ["4", "5", "6"], ["7"]]
    assert final == ["3", "6", "7"]
    assert [posting_id for posting_id, _ in picked] == ["posting-7"]
