"""
The daily board refresh, run by the refresh workflow:
`uv run python -m scripts.refresh_boards`. Fetches every directory board,
saves its jobs and embeds every open job that has none yet. Point it at the
hosted project by setting SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
"""

import logging
import sys
from datetime import UTC, datetime

from app.agents.orchestrator import refresh_boards
from app.config import Settings, get_settings
from app.db import service_db
from app.mail import alert_admin
from app.telemetry import configure_logging

logger = logging.getLogger("agent")


def run_refresh(settings: Settings) -> bool:
    """
    Runs the board refresh and emails the admin when it fails or can't reach
    some boards, at most once a day each. Returns whether the refresh finished.
    """
    today = datetime.now(UTC).date().isoformat()
    try:
        summary = refresh_boards(service_db(settings))
    except Exception as error:
        logger.exception("board refresh failed")
        alert_admin(
            settings,
            "Board refresh failed",
            [f"The daily board refresh stopped with an error: {error}", "Searches fetch boards live until the next refresh succeeds."],
            f"refresh-failed/{today}",
        )
        return False
    logger.info("board refresh finished", extra={key: value for key, value in summary.items() if key != "board_fetches"})
    unreachable = sorted(fetch["board"] for fetch in summary["board_fetches"] if fetch["outcome"] == "unreachable")
    if unreachable:
        alert_admin(
            settings,
            f"Board refresh couldn't reach {len(unreachable)} {'board' if len(unreachable) == 1 else 'boards'}",
            [
                f"The refresh saved {summary['jobs']:,} jobs from {summary['boards']} boards, but these failed twice in a row:",
                *unreachable,
                "Searches fetch these boards live; if they keep failing, check them on the admin page.",
            ],
            f"refresh-unreachable/{today}",
        )
    return True


if __name__ == "__main__":
    configure_logging()
    sys.exit(0 if run_refresh(get_settings()) else 1)
