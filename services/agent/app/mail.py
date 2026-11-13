import html
import logging

import resend

from app.config import Settings

logger = logging.getLogger("agent")


def send_email(settings: Settings, to: str, subject: str, body_html: str, idempotency_key: str | None = None) -> bool:
    """
    Sends one email through Resend and returns whether it went out. Without
    RESEND_API_KEY, or when Resend refuses it, the email is logged instead, so
    sending never fails the caller. A repeated idempotency key within 24 hours
    sends nothing new.
    """
    if not settings.resend_api_key:
        logger.info("email not sent: RESEND_API_KEY is not set", extra={"to": to, "subject": subject})
        return False
    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send(
            {"from": settings.email_from, "to": [to], "subject": subject, "html": body_html},
            {"idempotency_key": idempotency_key} if idempotency_key else None,
        )
    except Exception as error:
        logger.warning("sending email %r failed: %s", subject, error)
        return False
    return True


def alert_admin(settings: Settings, subject: str, lines: list[str], idempotency_key: str | None = None) -> bool:
    """Emails ADMIN_EMAIL an alert, one paragraph per line; without ADMIN_EMAIL it is logged instead."""
    if not settings.admin_email:
        logger.info("alert not sent: ADMIN_EMAIL is not set", extra={"subject": subject})
        return False
    body = "".join(f"<p>{html.escape(line)}</p>" for line in lines)
    return send_email(settings, settings.admin_email, f"[Job Scout] {subject}", body, idempotency_key)
