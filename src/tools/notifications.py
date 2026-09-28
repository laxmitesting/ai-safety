"""notifications.py: Dispatch regulatory alerts and review cards to external endpoints."""

import logging
from typing import Optional
import httpx

from configs.settings import (
    DISCORD_WEBHOOK_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

logger = logging.getLogger(__name__)


async def send_telegram_alert(
    title: str,
    message: str,
    rule_id: Optional[str] = None,
) -> bool:
    """Send a structured regulatory review card to Telegram using centralized settings."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram notification skipped: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in settings.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text_content = (
        f"🚨 *AISafetyCompliance Alert*\n\n"
        f"*Event:* {title}\n"
        f"*(Rule):* `{rule_id or 'N/A'}`\n\n"
        f"{message}"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text_content,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info("Successfully dispatched Telegram compliance notification.")
            return True
        except httpx.HTTPError as exc:
            logger.error(f"Failed to deliver Telegram notification: {exc}")
            return False


async def send_discord_alert(
    title: str,
    message: str,
    rule_id: Optional[str] = None,
) -> bool:
    """Send a structured embed card to Discord via webhook using centralized settings."""
    if not DISCORD_WEBHOOK_URL:
        logger.warning("Discord notification skipped: Missing DISCORD_WEBHOOK_URL in settings.")
        return False

    payload = {
        "username": "AISafetyCompliance Radar",
        "embeds": [
            {
                "title": f"🚨 {title}",
                "description": message,
                "color": 3447003,  # Blue/neutral info hex for radar
                "fields": [
                    {
                        "name": "Statutory Rule",
                        "value": f"`{rule_id or 'General'}`",
                        "inline": True,
                    }
                ],
            }
        ],
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            logger.info("Successfully dispatched Discord radar notification.")
            return True
        except httpx.HTTPError as exc:
            logger.error(f"Failed to deliver Discord notification: {exc}")
            return False