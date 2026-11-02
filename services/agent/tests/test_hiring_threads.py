from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import respx

from app.agents.hiring_threads.agent import API, HiringPost, extract_jobs, recent_posts
from app.agents.schemas import HiringJob, HiringJobs, Usage

WHEN = datetime(2026, 10, 1, 15, 1, tzinfo=UTC)


class FakeMessages:
    def __init__(self, jobs: list[HiringJob]):
        self.jobs = jobs

    def parse(self, **kwargs: Any) -> Any:
        return SimpleNamespace(parsed_output=HiringJobs(jobs=self.jobs), usage=SimpleNamespace(input_tokens=100, output_tokens=20))


@respx.mock
def test_recent_posts_reads_the_latest_hiring_threads():
    respx.get(f"{API}/search_by_date").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {"objectID": "3", "title": "Ask HN: Who wants to be hired? (November 2026)"},
                    {"objectID": "2", "title": "Ask HN: Who is hiring? (November 2026)"},
                    {"objectID": "1", "title": "Ask HN: Who is hiring? (October 2026)"},
                ]
            },
        )
    )
    child = {"id": 21, "text": "Acme | Engineer | <i>Remote</i>", "created_at": "2026-10-01T15:01:00.000Z"}
    respx.get(f"{API}/items/2").mock(return_value=httpx.Response(200, json={"children": [child, {"id": 22, "text": None}]}))
    respx.get(f"{API}/items/1").mock(return_value=httpx.Response(200, json={"children": []}))

    [post] = recent_posts()

    assert (post.id, post.text, post.posted_at) == ("21", "Acme | Engineer | Remote", WHEN)


def test_extract_jobs_numbers_each_posts_roles_and_drops_bad_entries():
    jobs = [
        HiringJob(post=0, company="Prairie Learn", title="Backend Engineer", location="Remote (US)", workplace_type="remote"),
        HiringJob(post=0, company="Prairie Learn", title="Frontend Engineer", location=None, workplace_type=None),
        HiringJob(post=5, company="Ghost", title="Engineer", location=None, workplace_type=None),
    ]
    client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(jobs)))
    usage = Usage()

    backend, frontend = extract_jobs(client, "claude-haiku-5-5", [HiringPost("21", "PrairieLearn is hiring", WHEN)], usage)

    assert (backend.source, backend.board, backend.external_id) == ("hackernews", "prairie-learn", "21-1")
    assert backend.url == "https://news.ycombinator.com/item?id=21" and backend.description == "PrairieLearn is hiring"
    assert backend.workplace_type == "remote" and backend.posted_at == WHEN
    assert frontend.external_id == "21-2"
    assert usage.input_tokens == 100
