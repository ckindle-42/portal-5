"""Tests for portal_pipeline.notifications — no network required."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set env vars before importing — notifications read them at module load
os.environ.setdefault("NOTIFICATIONS_ENABLED", "false")


class TestAlertEvent:
    """AlertEvent format methods."""

    def test_format_slack(self):
        from portal_pipeline.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.BACKEND_DOWN,
            message="Backend 'ollama-1' has been unhealthy for 3 consecutive checks.",
            backend_id="ollama-1",
        )
        formatted = event.format_slack()
        assert ":warning:" in formatted
        assert "backend_down" in formatted  # enum value, not ALL_CAPS
        assert "ollama-1" in formatted

    def test_format_telegram(self):
        from portal_pipeline.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.ALL_BACKENDS_DOWN,
            message="All backends are unhealthy. Portal 5 cannot serve requests.",
        )
        formatted = event.format_telegram()
        assert "[CRITICAL]" in formatted
        assert "all_backends_down" in formatted  # type value

    def test_format_pushover_truncates(self):
        from portal_pipeline.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.BACKEND_DOWN,
            message="x" * 600,  # over 512 limit
            backend_id="test",
        )
        formatted = event.format_pushover()
        assert len(formatted) <= 512

    def test_format_email(self):
        from portal_pipeline.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.CONFIG_ERROR,
            message="backends.yaml not found",
        )
        formatted = event.format_email()
        assert "<b>" in formatted
        assert "CONFIG_ERROR" in formatted


class TestSummaryEvent:
    """SummaryEvent format methods."""

    def test_format_slack(self):
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
            total_requests=1234,
            requests_by_workspace={"auto": 500, "auto-coding": 734},
            healthy_backends=2,
            total_backends=3,
            uptime_seconds=36000.0,
        )
        formatted = event.format_slack()
        assert "Daily Usage Summary" in formatted
        assert "1,234" in formatted  # thousands separator
        assert "auto-coding" in formatted
        assert "2/3" in formatted

    def test_format_telegram(self):
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
            total_requests=100,
            requests_by_workspace={"auto": 100},
            healthy_backends=1,
            total_backends=1,
            uptime_seconds=7200.0,
        )
        formatted = event.format_telegram()
        assert "Daily Summary" in formatted
        assert "100" in formatted

    def test_format_pushover(self):
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
            total_requests=5000,
            requests_by_workspace={"auto": 3000, "auto-coding": 2000},
            healthy_backends=2,
            total_backends=2,
            uptime_seconds=86400.0,
        )
        formatted = event.format_pushover()
        assert len(formatted) <= 512
        assert "5,000" in formatted  # thousands separator


class TestSlackChannel:
    """Slack notification channel."""

    @pytest.mark.asyncio
    async def test_send_alert_skips_when_not_configured(self):
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.events import AlertEvent, EventType

        channel = SlackChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        # Should not raise even though webhook URL is not set
        await channel.send(event)

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.events import AlertEvent, EventType

        with patch.dict(os.environ, {"SLACK_ALERT_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            channel = SlackChannel()
            event = AlertEvent(
                type=EventType.BACKEND_DOWN,
                message="Test alert",
                backend_id="test-backend",
            )

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value.raise_for_status = MagicMock()
                await channel.send(event)
                mock_post.assert_called_once()


class TestTelegramChannel:
    """Telegram notification channel."""

    @pytest.mark.asyncio
    async def test_send_alert_skips_when_not_configured(self):
        from portal_pipeline.notifications.channels.telegram import TelegramChannel
        from portal_pipeline.notifications.events import AlertEvent, EventType

        channel = TelegramChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        await channel.send(event)  # Should not raise


class TestEmailChannel:
    """Email notification channel."""

    @pytest.mark.asyncio
    async def test_send_alert_skips_when_not_configured(self):
        from portal_pipeline.notifications.channels.email import EmailChannel
        from portal_pipeline.notifications.events import AlertEvent, EventType

        channel = EmailChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        await channel.send(event)  # Should not raise


class TestPushoverChannel:
    """Pushover notification channel."""

    @pytest.mark.asyncio
    async def test_send_alert_skips_when_not_configured(self):
        from portal_pipeline.notifications.channels.pushover import PushoverChannel
        from portal_pipeline.notifications.events import AlertEvent, EventType

        channel = PushoverChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        await channel.send(event)  # Should not raise


class TestNotificationDispatcher:
    """Dispatcher threshold tracking and debouncing."""

    def test_dispatcher_disabled_by_default(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "false"}):
            # Re-import to pick up patched env
            import importlib

            import portal_pipeline.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal_pipeline.notifications.dispatcher import (
                NotificationDispatcher,
            )

            disp = NotificationDispatcher()
            mock_channel = MagicMock()
            mock_channel.name = "test"
            disp.add_channel(mock_channel)
            assert len(disp._channels) == 0

    def test_threshold_tracking_consecutive_failures(self):
        with patch.dict(
            os.environ, {"NOTIFICATIONS_ENABLED": "true", "ALERT_BACKEND_DOWN_THRESHOLD": "3"}
        ):
            import importlib

            import portal_pipeline.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal_pipeline.notifications.dispatcher import (
                NotificationDispatcher,
            )

            disp = NotificationDispatcher()

            mock_registry = MagicMock()
            mock_backend = MagicMock()
            mock_backend.healthy = False
            mock_registry._backends = {"test-backend": mock_backend}

            # Two checks — should accumulate but not fire
            disp.check_thresholds_and_alert(mock_registry)
            assert disp._failure_counts["test-backend"] == 1
            disp.check_thresholds_and_alert(mock_registry)
            assert disp._failure_counts["test-backend"] == 2

            # Third check — crosses threshold (3 == ALERT_BACKEND_DOWN_THRESHOLD=3)
            # We assert the counter reached the threshold value — the actual async
            # dispatch is tested separately in async tests.
            disp.check_thresholds_and_alert(mock_registry)
            assert disp._failure_counts["test-backend"] == 3

    def test_recovery_fires_event(self):
        with patch.dict(
            os.environ, {"NOTIFICATIONS_ENABLED": "true", "ALERT_BACKEND_DOWN_THRESHOLD": "2"}
        ):
            import importlib

            import portal_pipeline.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal_pipeline.notifications.dispatcher import (
                NotificationDispatcher,
            )
            from portal_pipeline.notifications.events import EventType

            disp = NotificationDispatcher()
            mock_backend = MagicMock()
            mock_backend.healthy = False
            mock_registry = MagicMock()
            mock_registry._backends = {"recovering": mock_backend}

            # Push it past threshold while unhealthy
            disp._failure_counts["recovering"] = 2

            # Now it recovers
            mock_backend.healthy = True

            with (
                patch.object(disp, "dispatch", new_callable=AsyncMock) as mock_dispatch,
                patch("asyncio.ensure_future"),
            ):
                disp.check_thresholds_and_alert(mock_registry)
                mock_dispatch.assert_called_once()
                event = mock_dispatch.call_args[0][0]
                assert event.type == EventType.BACKEND_RECOVERED

    def test_all_backends_down_fires_once(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            import importlib

            import portal_pipeline.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal_pipeline.notifications.dispatcher import (
                NotificationDispatcher,
            )
            from portal_pipeline.notifications.events import EventType

            disp = NotificationDispatcher()

            backend1 = MagicMock()
            backend1.healthy = False
            backend2 = MagicMock()
            backend2.healthy = False
            mock_registry = MagicMock()
            mock_registry._backends = {"b1": backend1, "b2": backend2}

            with (
                patch.object(disp, "dispatch", new_callable=AsyncMock) as mock_dispatch,
                patch("asyncio.ensure_future"),
            ):
                disp.check_thresholds_and_alert(mock_registry)
                # Should fire ALL_BACKENDS_DOWN
                all_down_events = [
                    c[0][0]
                    for c in mock_dispatch.call_args_list
                    if c[0][0].type == EventType.ALL_BACKENDS_DOWN
                ]
                assert len(all_down_events) == 1

            # Second cycle — should NOT fire again (debounced)
            with (
                patch.object(disp, "dispatch", new_callable=AsyncMock) as mock_dispatch,
                patch("asyncio.ensure_future"),
            ):
                disp.check_thresholds_and_alert(mock_registry)
                all_down_events = [
                    c[0][0]
                    for c in mock_dispatch.call_args_list
                    if c[0][0].type == EventType.ALL_BACKENDS_DOWN
                ]
                assert len(all_down_events) == 0

    def test_all_down_clears_on_recovery(self):
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            import importlib

            import portal_pipeline.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal_pipeline.notifications.dispatcher import (
                NotificationDispatcher,
            )

            disp = NotificationDispatcher()
            disp._alerted_all_down = True

            b1 = MagicMock()
            b1.healthy = True
            mock_registry = MagicMock()
            mock_registry._backends = {"b1": b1}

            with (
                patch.object(disp, "dispatch", new_callable=AsyncMock),
                patch("asyncio.ensure_future"),
            ):
                disp.check_thresholds_and_alert(mock_registry)
            assert disp._alerted_all_down is False


class TestNotificationChannelInterface:
    """Base class interface — channels must implement send_alert/send_summary."""

    def test_channel_has_name_property(self):
        from portal_pipeline.notifications.channels import NotificationChannel

        assert hasattr(NotificationChannel, "name")
        assert hasattr(NotificationChannel, "send_alert")
        assert hasattr(NotificationChannel, "send_summary")

    def test_all_channels_registered(self):
        """Verify all available channels can be instantiated."""
        from portal_pipeline.notifications.channels.slack import SlackChannel
        from portal_pipeline.notifications.channels.telegram import TelegramChannel

        channels = [
            SlackChannel(),
            TelegramChannel(),
        ]
        assert all(hasattr(c, "name") for c in channels)
        names = [c.name for c in channels]
        assert "Slack" in names
        assert "Telegram" in names
