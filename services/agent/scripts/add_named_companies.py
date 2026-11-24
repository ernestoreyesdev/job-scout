"""
Adds to the company directory, by name, the companies of every saved Hacker
News job and of jobs users added by hand from links on no known board:
`uv run python -m scripts.add_named_companies`. Each name is tried on every
system's spellings and the companies found are named and labeled, so it needs
ANTHROPIC_API_KEY. Companies the directory already lists by name are skipped.
Point it at the hosted project by setting SUPABASE_URL and
SUPABASE_SERVICE_ROLE_KEY for that project. Safe to rerun.
"""

import sys

import anthropic

from app.agents.orchestrator import ImportResult, add_companies_by_name, add_hiring_thread_companies
from app.config import get_settings
from app.db import service_db
from app.sources import board_from_url
from app.telemetry import CallLog, RecordingClient


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        sys.exit("Set ANTHROPIC_API_KEY: the companies found are named and labeled with Claude.")
    service = service_db(settings)
    calls = CallLog()
    client = RecordingClient(anthropic.Anthropic(api_key=settings.anthropic_api_key), calls)
    try:
        report("Hacker News", add_hiring_thread_companies(service, client, settings, None))
        added = service.select("applications", {"select": "posting:postings(company,url)", "added_by": "eq.user"})
        names = [row["posting"]["company"] for row in added if not board_from_url(row["posting"]["url"])]
        report("Added by hand", add_companies_by_name(service, client, settings, names, "link"))
    finally:
        calls.save(service)


def report(label: str, result: ImportResult | None) -> None:
    if result is None:
        print(f"{label}: every company is already in the directory")
        return
    print(f"{label}: added {len(result.added):,}, not found {len(result.not_found):,}, already listed {result.existing:,}")
    for name in result.added:
        print(f"  Added {name}")


if __name__ == "__main__":
    main()
