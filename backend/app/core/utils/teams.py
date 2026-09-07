"""Send messages to a Microsoft Teams channel via an incoming webhook.

Uses the classic Office 365 connector-card format, which is still accepted by
incoming webhooks. To use it, create an *Incoming Webhook* connector in the
target channel and put its URL in ``TEAMS_WEBHOOK_URL`` (see ``.env.example``).
"""

import requests

from ..config import TEAMS_WEBHOOK_URL
from ..logger import get_logger

logger = get_logger(__name__)

_REQUEST_TIMEOUT = 10  # seconds


def send_teams_message(text: str, title: str | None = None, webhook_url: str | None = None) -> bool:
    """Post ``text`` to a Microsoft Teams channel and return whether it succeeded.

    Args:
        text: The message body to send (plain text or simple Markdown).
        title: Optional card title shown as a header above the message.
        webhook_url: Optional Teams incoming-webhook URL. Defaults to the
            ``TEAMS_WEBHOOK_URL`` config value; when neither is set the call is
            a no-op that logs a warning and returns False.

    Returns:
        True when Teams accepted the message (HTTP 2xx), otherwise False.
    """
    url = webhook_url or TEAMS_WEBHOOK_URL
    if not url:
        logger.warning(
            "No Teams webhook URL configured; skipping message. "
            "Set TEAMS_WEBHOOK_URL in the environment."
        )
        return False

    payload = _build_payload(text, title)

    try:
        response = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info(
            "Teams message sent: title=%r, status_code=%s",
            title,
            response.status_code,
        )
        return True

    except Exception as exc:
        failed_response = getattr(exc, "response", None)
        details = {
            "title": title,
            "status_code": getattr(failed_response, "status_code", None),
            "response_text": getattr(failed_response, "text", None),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }
        logger.exception(
            "Failed to send Teams message. Details: %s",
            details,
        )
        return False


def _build_payload(text: str, title: str | None) -> dict:
    """Build an Office 365 connector-card payload accepted by incoming webhooks."""
    payload: dict = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title or text[:200],
    }
    sections = [{"text": text}]
    if title:
        payload["title"] = title
    payload["sections"] = sections
    return payload
