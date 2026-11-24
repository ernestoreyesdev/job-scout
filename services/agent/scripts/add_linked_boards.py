"""
Adds to the company directory the job boards of jobs users added by link
before links did that themselves: `uv run python -m scripts.add_linked_boards`.
Each board joins with every open job it lists and origin "link", and its
company is labeled when ANTHROPIC_API_KEY is set. Boards already in the
directory, links on no known board and boards that can't be reached are left
out. Point it at the hosted project by setting SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY for that project. Safe to rerun.
"""

from typing import cast

from app.agents.discovery.agent import name_companies
from app.agents.orchestrator import Board, fetch_boards, label_if_new, record_board_checks, remove_duplicate_names
from app.config import get_settings
from app.db import service_db
from app.sources import board_from_url, default_name, fetch_live
from app.sources.base import CompanyBoard, SourceName
from app.telemetry import CallLog, RecordingClient


def main() -> None:
    settings = get_settings()
    service = service_db(settings)
    added = service.select("applications", {"select": "posting:postings(url)", "added_by": "eq.user"})
    linked = {board for row in added if (board := board_from_url(row["posting"]["url"]))}
    known = {(c["source"], c["board"]) for c in service.select("companies", {"select": "source,board"})}
    boards = [Board(source, slug, default_name(source, slug), "link") for source, slug in sorted(linked - known)]
    print(f"{len(added):,} jobs added by users, {len(linked):,} boards they're on, {len(boards):,} not in the directory")
    if not boards:
        return

    fetched, gone, unreachable, _ = fetch_boards(boards, fetch_live, lambda _: None)
    record_board_checks(service, boards, fetched, [])
    remove_duplicate_names(service)
    for source, slug in gone:
        print(f"Gone: {source}/{slug}")
    for board in unreachable:
        print(f"Unreachable: {board}")
    for (source, slug), jobs in fetched.items():
        print(f"Added {source}/{slug} with {len(jobs):,} open jobs")

    if not fetched:
        return
    if not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY, so the new companies stay unlabeled.")
        return
    import anthropic

    calls = CallLog()
    client = RecordingClient(anthropic.Anthropic(api_key=settings.anthropic_api_key), calls)
    try:
        for board in boards:
            if board.key in fetched:
                jobs = fetched[board.key]
                found = CompanyBoard(cast(SourceName, board.source), board.board, jobs[0].company if jobs else board.name, jobs)
                label_if_new(found, client, settings, service, name_companies)
    finally:
        calls.save(service)
    print("Labeled the new companies")


if __name__ == "__main__":
    main()
