"""tests/test_notifications.py: Unit tests for Telegram and Discord notification tools."""

from unittest.mock import AsyncMock, patch
import pytest

from src.tools.notifications import send_discord_alert, send_telegram_alert


@pytest.mark.asyncio
async def test_send_telegram_alert_success(monkeypatch):
    """Asserts Telegram alert succeeds when credentials exist and HTTP 200 returns."""
    monkeypatch.setattr("src.tools.notifications.TELEGRAM_BOT_TOKEN", "mock_bot_token")
    monkeypatch.setattr("src.tools.notifications.TELEGRAM_CHAT_ID", "123456789")

    mock_resp = AsyncMock()
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        success = await send_telegram_alert(
            title="CI Audit Blocked",
            message="Deceptive system persona detected.",
            rule_id="eu_ai_act_art50",
        )

        assert success is True
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"]["chat_id"] == "123456789"
        assert "eu_ai_act_art50" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_send_telegram_alert_missing_credentials(monkeypatch):
    """Asserts Telegram alert gracefully returns False when tokens are missing."""
    monkeypatch.setattr("src.tools.notifications.TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr("src.tools.notifications.TELEGRAM_CHAT_ID", "")

    success = await send_telegram_alert(
        title="CI Audit Blocked",
        message="Deceptive system persona detected.",
    )
    assert success is False


@pytest.mark.asyncio
async def test_send_discord_alert_success(monkeypatch):
    """Asserts Discord webhook succeeds when webhook URL exists and HTTP 200 returns."""
    monkeypatch.setattr(
        "src.tools.notifications.DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/mock/test",
    )

    mock_resp = AsyncMock()
    mock_resp.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        success = await send_discord_alert(
            title="New Regulatory Feed Item",
            message="UK DUAA statutory update detected.",
            rule_id="uk_duaa_s80",
        )

        assert success is True
        mock_post.assert_awaited_once()
        _, kwargs = mock_post.call_args
        embeds = kwargs["json"]["embeds"]
        assert len(embeds) == 1
        assert "New Regulatory Feed Item" in embeds[0]["title"]


@pytest.mark.asyncio
async def test_send_discord_alert_missing_webhook(monkeypatch):
    """Asserts Discord alert gracefully returns False when webhook URL is absent."""
    monkeypatch.setattr("src.tools.notifications.DISCORD_WEBHOOK_URL", "")

    success = await send_discord_alert(
        title="New Regulatory Feed Item",
        message="UK DUAA statutory update detected.",
    )
    assert success is False