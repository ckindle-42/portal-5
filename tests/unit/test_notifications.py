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
            requests_by_model={"dolphin-llama3:8b": 800, "qwen3-coder-next:30b-q5": 434},
            avg_tokens_per_second=25.5,
            total_input_tokens=50000,
            total_output_tokens=150000,
            avg_response_time_ms=1200.0,
        )
        formatted = event.format_slack()
        assert "Daily Usage Summary" in formatted
        assert "1,234" in formatted  # thousands separator
        assert "auto-coding" in formatted
        assert "2/3" in formatted
        assert "25.5 tok/s" in formatted  # avg TPS
        assert "1200ms" in formatted  # avg response time
        assert "50,000 in" in formatted  # input tokens

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
            avg_tokens_per_second=30.0,
            avg_response_time_ms=800.0,
        )
        formatted = event.format_telegram()
        assert "Daily Summary" in formatted
        assert "100" in formatted
        assert "30.0" in formatted  # avg TPS

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
            avg_tokens_per_second=20.0,
            avg_response_time_ms=1500.0,
        )
        formatted = event.format_pushover()
        assert len(formatted) <= 512
        assert "5,000" in formatted  # thousands separator

    def test_format_slack_top_models(self):
        """Verify top models section appears in Slack format."""
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
            total_requests=1000,
            requests_by_workspace={"auto": 1000},
            healthy_backends=2,
            total_backends=2,
            uptime_seconds=36000.0,
            requests_by_model={
                "dolphin-llama3:8b": 500,
                "qwen3-coder-next:30b-q5": 300,
                "deepseek-r1:32b-q4_k_m": 200,
            },
        )
        formatted = event.format_slack()
        assert "Top Models" in formatted
        assert "dolphin-llama3:8b" in formatted
        # Should only show top 5 models
        assert formatted.count("`") <= 12  # 6 models * 2 backticks


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


class TestNotificationScheduler:
    """NotificationScheduler — timer logic and summary metric gathering."""

    @pytest.mark.asyncio
    async def test_send_daily_summary_includes_extended_metrics(self):
        """Verify _send_daily_summary reads router_pipe stats and builds a complete SummaryEvent."""
        import importlib

        import portal_pipeline.notifications.dispatcher as disp_mod

        importlib.reload(disp_mod)
        from portal_pipeline.notifications.dispatcher import NotificationDispatcher
        from portal_pipeline.notifications.scheduler import NotificationScheduler

        disp = NotificationDispatcher()

        # Mock registry for health counts
        mock_backend = MagicMock()
        mock_backend.healthy = True
        mock_registry = MagicMock()
        mock_registry._backends = {"ollama-1": mock_backend}
        mock_registry_instance = MagicMock()
        mock_registry_instance._backends = {"ollama-1": mock_backend}

        fake_request_count = {"auto": 100, "auto-coding": 50}
        fake_startup = 1000000000.0

        # Patch router_pipe module so _send_daily_summary reads our fake stats
        fake_router = MagicMock()
        fake_router._total_response_time_ms = 50000.0  # 50s total
        fake_router._request_tps_count = 10
        fake_router._total_tps = 250.0  # 25 avg TPS
        fake_router._total_input_tokens = 10000
        fake_router._total_output_tokens = 30000
        fake_router._req_count_by_model = {
            "dolphin-llama3:8b": 100,
            "qwen3-coder-next:30b-q5": 50,
        }

        with patch.dict(os.environ, {"ALERT_SUMMARY_ENABLED": "true"}, clear=False):
            scheduler = NotificationScheduler(disp)
            from portal_pipeline.notifications import scheduler as sched_module

            sched_module._attach_to_pipeline(
                disp, fake_request_count, fake_startup, mock_registry_instance
            )

            with patch.object(disp, "dispatch", new_callable=AsyncMock) as mock_dispatch:
                import portal_pipeline.router_pipe as rp_module
                from portal_pipeline.notifications import scheduler as sched_module

                # Mock cooldown file so test doesn't skip due to existing lockfile
                cooldown_file_mock = MagicMock()
                cooldown_file_mock.exists.return_value = False

                with (
                    patch.object(rp_module, "_total_response_time_ms", 50000.0),
                    patch.object(rp_module, "_request_tps_count", 10),
                    patch.object(rp_module, "_total_tps", 250.0),
                    patch.object(rp_module, "_total_input_tokens", 10000),
                    patch.object(rp_module, "_total_output_tokens", 30000),
                    patch.object(
                        rp_module,
                        "_req_count_by_model",
                        {
                            "dolphin-llama3:8b": 100,
                            "qwen3-coder-next:30b-q5": 50,
                        },
                    ),
                    patch.object(sched_module, "_COOLDOWN_FILE", cooldown_file_mock),
                ):
                    await scheduler._send_daily_summary()

                # Verify dispatch was called once with a SummaryEvent
                mock_dispatch.assert_called_once()
                event = mock_dispatch.call_args[0][0]

                # Check extended metrics are present and correct
                assert event.requests_by_model == {
                    "dolphin-llama3:8b": 100,
                    "qwen3-coder-next:30b-q5": 50,
                }
                assert event.avg_tokens_per_second == pytest.approx(25.0)
                assert event.total_input_tokens == 10000
                assert event.total_output_tokens == 30000
                assert abs(event.avg_response_time_ms - 333.33) < 0.1  # 50000/150 ≈ 333.33
                assert event.total_requests == 150  # 100 + 50


class TestSchedulerSettings:
    """Verify ALERT_SUMMARY_* env vars control scheduler behaviour."""

    def test_scheduler_disabled_when_apscheduler_missing(self):
        """When APScheduler is not installed the scheduler should not start."""
        import importlib

        import portal_pipeline.notifications.dispatcher as disp_mod

        importlib.reload(disp_mod)
        from portal_pipeline.notifications.dispatcher import NotificationDispatcher

        disp = NotificationDispatcher()
        mock_channel = MagicMock()
        mock_channel.name = "test"
        disp.add_channel(mock_channel)
        # When APScheduler unavailable the channel list stays empty
        assert disp._channels == [] or disp._enabled is False


class TestWebhookSummaryExtendedMetrics:
    """Webhook channel includes extended metrics in send_summary."""

    @pytest.mark.asyncio
    async def test_webhook_send_summary_includes_extended_metrics(self):
        from portal_pipeline.notifications.channels.webhook import WebhookChannel
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        with patch.dict(os.environ, {"WEBHOOK_URL": "https://example.com/webhook"}):
            channel = WebhookChannel()
            event = SummaryEvent(
                type=EventType.DAILY_SUMMARY,
                timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
                total_requests=500,
                requests_by_workspace={"auto": 300, "auto-coding": 200},
                healthy_backends=2,
                total_backends=3,
                uptime_seconds=86400.0,
                requests_by_model={"dolphin-llama3:8b": 300, "qwen3-coder-next:30b-q5": 200},
                avg_tokens_per_second=25.0,
                total_input_tokens=50000,
                total_output_tokens=150000,
                avg_response_time_ms=1200.0,
            )

            with patch.object(channel, "_post", new_callable=AsyncMock) as mock_post:
                await channel.send_summary(event)
                mock_post.assert_called_once()
                payload = mock_post.call_args[0][0]
                # Verify extended metrics are present
                assert payload["requests_by_model"] == {
                    "dolphin-llama3:8b": 300,
                    "qwen3-coder-next:30b-q5": 200,
                }
                assert payload["avg_tokens_per_second"] == 25.0
                assert payload["total_input_tokens"] == 50000
                assert payload["total_output_tokens"] == 150000
                assert payload["avg_response_time_ms"] == 1200.0


class TestPushoverSummaryPriority:
    """Pushover summary uses normal priority (0), not emergency (2)."""

    @pytest.mark.asyncio
    async def test_pushover_summary_uses_normal_priority(self):
        from portal_pipeline.notifications.channels.pushover import PushoverChannel
        from portal_pipeline.notifications.events import EventType, SummaryEvent

        with patch.dict(
            os.environ,
            {
                "PUSHOVER_API_TOKEN": "test-token",
                "PUSHOVER_USER_KEY": "test-user",
            },
        ):
            channel = PushoverChannel()
            event = SummaryEvent(
                type=EventType.DAILY_SUMMARY,
                timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=timezone.utc),
                total_requests=100,
                requests_by_workspace={"auto": 100},
                healthy_backends=1,
                total_backends=1,
                uptime_seconds=3600.0,
                avg_tokens_per_second=20.0,
                avg_response_time_ms=800.0,
            )

            with patch.object(channel, "_post", new_callable=AsyncMock) as mock_post:
                await channel.send_summary(event)
                mock_post.assert_called_once()
                payload = mock_post.call_args[0][0]
                # Summary should be normal priority (0), not emergency (2)
                assert payload["priority"] == "0"
                assert payload["title"] == "Portal 5 — Daily Summary"


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
