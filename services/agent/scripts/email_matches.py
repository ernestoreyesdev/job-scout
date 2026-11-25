"""
The daily searches, run by the refresh workflow after the board refresh:
`uv run python -m scripts.email_matches`. Runs every search a user marked and
emails them the new jobs scoring 70 or more. Uses ANTHROPIC_API_KEY for the
scoring. Point it at the hosted project by setting SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
"""

import logging
import sys

import anthropic

from app.agents.alerts import run_alerts
from app.config import get_settings
from app.db import service_db
from app.telemetry import configure_logging, configure_sentry

logger = logging.getLogger("agent")


def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.error("daily searches need ANTHROPIC_API_KEY")
        return 1
    summary = run_alerts(service_db(settings), settings, anthropic.Anthropic(api_key=settings.anthropic_api_key))
    logger.info("daily searches finished", extra=summary)
    return 0


if __name__ == "__main__":
    configure_logging()
    configure_sentry()
    sys.exit(main())
