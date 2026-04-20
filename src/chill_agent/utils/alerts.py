"""Discord and Slack webhook alerts."""

from __future__ import annotations

import requests
import structlog

logger = structlog.get_logger()


def send_alert(message: str, discord_url: str = "", slack_url: str = "") -> None:
    """Send an alert to Discord and/or Slack. Silently swallows errors (alerts are best-effort)."""
    if discord_url:
        _send_discord(message, discord_url)
    if slack_url:
        _send_slack(message, slack_url)
    if not discord_url and not slack_url:
        logger.warning("alert_no_webhook_configured", message=message)


def _send_discord(message: str, url: str) -> None:
    try:
        resp = requests.post(
            url,
            json={"content": message[:2000]},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("alert_sent_discord")
    except Exception as e:
        logger.error("alert_discord_failed", error=str(e))


def _send_slack(message: str, url: str) -> None:
    try:
        resp = requests.post(
            url,
            json={"text": message[:3000]},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("alert_sent_slack")
    except Exception as e:
        logger.error("alert_slack_failed", error=str(e))
