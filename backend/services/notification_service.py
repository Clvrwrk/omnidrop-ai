"""
OmniDrop AI — Notification Service

Channel-agnostic adapter pattern for bounce-back notifications.
Alpha: SlackAdapter (Slack Incoming Webhooks — one-way, no bot required).
Future: AccuLynxAdapter, SignalAdapter (same interface).

The bounce_back Celery task calls get_notification_adapter(channel_config)
and calls adapter.send(message) — it never calls Slack directly.
"""

import logging
from abc import ABC, abstractmethod
from typing import TypedDict

import httpx

logger = logging.getLogger(__name__)


# ── Message Schema ────────────────────────────────────────────────────────────


class NotificationMessage(TypedDict):
    """Structured notification payload for bounce-back alerts."""

    location_name: str
    acculynx_job_id: str | None        # None renders as "N/A"
    file_name: str
    document_summary: str
    clarification_question: str
    job_deep_link: str                 # e.g. "https://omnidrop.dev/dashboard/ops/jobs/{job_id}"


# ── Abstract Base ─────────────────────────────────────────────────────────────


class NotificationAdapter(ABC):
    """
    Abstract base for all notification channel adapters.

    Concrete adapters implement send() and return a status dict so that
    the Celery task never has to know which channel is being used.
    """

    @abstractmethod
    def send(self, message: NotificationMessage) -> dict:
        """
        Send a notification message.

        Returns:
            {
                "status": "sent" | "failed",
                "channel": str,
                "error": str | None,
            }
        """


# ── Slack Adapter ─────────────────────────────────────────────────────────────


class SlackAdapter(NotificationAdapter):
    """
    Sends notifications via Slack Incoming Webhooks.
    One-way delivery — no bot token or Slack App required.
    Uses httpx (sync) because this is called from Celery tasks.
    """

    CHANNEL = "slack"

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send(self, message: NotificationMessage) -> dict:
        """POST a Block Kit message to the configured Slack Incoming Webhook URL."""
        job_id_display = message["acculynx_job_id"] or "N/A"

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "OmniDrop \u2014 Document Needs Clarification",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"\U0001f4cd *Location:* {message['location_name']}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"\U0001f4c4 *Job:* {job_id_display}"
                                f"  |  *File:* {message['file_name']}"
                            ),
                        },
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"\U0001f50d *What we detected:* {message['document_summary']}"
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Question:*\n{message['clarification_question']}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"\u27a1\ufe0f  <{message['job_deep_link']}|View document in OmniDrop>"
                        ),
                    },
                },
            ]
        }

        try:
            response = httpx.post(
                self._webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                "SlackAdapter.send succeeded",
                extra={"file_name": message["file_name"]},
            )
            return {"status": "sent", "channel": self.CHANNEL, "error": None}
        except httpx.HTTPError as exc:
            logger.error(
                "SlackAdapter.send failed",
                extra={"file_name": message["file_name"], "error": str(exc)},
            )
            return {"status": "failed", "channel": self.CHANNEL, "error": str(exc)}


# ── Factory ───────────────────────────────────────────────────────────────────


def get_notification_adapter(channel_config: dict) -> NotificationAdapter | None:
    """
    Build the correct NotificationAdapter from a locations.notification_channels
    JSONB config dict.

    Returns None when no known channel is configured — callers must handle the
    no-channel case gracefully (log a warning, don't crash the Celery task).

    Example channel_config (stored per-location in Supabase):
        {"slack": {"webhook_url": "https://hooks.slack.com/services/..."}}
    """
    slack_config = channel_config.get("slack", {})
    webhook_url = slack_config.get("webhook_url")
    if webhook_url:
        return SlackAdapter(webhook_url=webhook_url)

    logger.warning(
        "get_notification_adapter: no supported channel found in channel_config"
    )
    return None
