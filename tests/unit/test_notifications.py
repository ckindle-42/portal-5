"""Tests for portal.platform.inference.notifications — no network required."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("NOTIFICATIONS_ENABLED", "false")


class TestAlertEvent:
    """AlertEvent format methods."""

    def test_format_slack(self):
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.BACKEND_DOWN,
            message="Backend 'ollama-1' has been unhealthy for 3 consecutive checks.",
            backend_id="ollama-1",
        )
        formatted = event.format_slack()
        assert ":warning:" in formatted
        assert "backend down" in formatted
        assert "ollama-1" in formatted

    def test_format_telegram(self):
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.ALL_BACKENDS_DOWN,
            message="All backends are unhealthy. Portal 5 cannot serve requests.",
        )
        formatted = event.format_telegram()
        assert "[CRITICAL]" in formatted
        assert "all backends down" in formatted  # type value

    def test_format_pushover_truncates(self):
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.BACKEND_DOWN,
            message="x" * 600,  # over 512 limit
            backend_id="test",
        )
        formatted = event.format_pushover()
        assert len(formatted) <= 512

    def test_format_email(self):
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        event = AlertEvent(
            type=EventType.CONFIG_ERROR,
            message="backends.yaml not found",
        )
        formatted = event.format_email()
        assert "<b>" in formatted
        assert "CONFIG ERROR" in formatted


class TestSummaryEvent:
    """SummaryEvent format methods."""

    def test_format_slack(self):
        from portal.platform.inference.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=UTC),
            report_date="2026-03-29",
            total_requests=1234,
            requests_by_workspace={"auto": 500, "auto-coding": 734},
            healthy_backends=2,
            total_backends=3,
            uptime_seconds=36000.0,
            requests_by_model={"dolphin-llama3:8b": 800, "qwen3-coder-next:30b-q5": 434},
            avg_tokens_per_second=25.5,
            ttft_median_seconds=0.45,
            ttft_sample_count=4,
            total_input_tokens=50000,
            total_output_tokens=150000,
            avg_response_time_ms=1200.0,
        )
        formatted = event.format_slack()
        assert "Daily Summary" in formatted
        assert "2026-03-29" in formatted  # report date
        assert "1,234" in formatted  # thousands separator
        assert "auto-coding" in formatted
        assert "2/3" in formatted
        assert "25.5 tok/s" in formatted  # avg TPS
        assert "TTFT median (n=4):* 0.45s" in formatted
        assert "1200ms" in formatted  # avg response time
        assert "50,000 in" in formatted  # input tokens

    def test_format_telegram(self):
        from portal.platform.inference.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=UTC),
            report_date="2026-03-29",
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

    def test_ttft_median_includes_sample_count_in_each_format(self):
        from portal.platform.inference.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=UTC),
            report_date="2026-03-29",
            total_requests=100,
            requests_by_workspace={"auto": 100},
            healthy_backends=1,
            total_backends=1,
            uptime_seconds=7200.0,
            ttft_median_seconds=0.35,
            ttft_sample_count=7,
        )

        formatted = (
            event.format_slack(),
            event.format_telegram(),
            event.format_email(),
            event.format_pushover(),
        )
        assert all("n=7" in item for item in formatted)

    def test_format_pushover(self):
        from portal.platform.inference.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=UTC),
            report_date="2026-03-29",
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
        from portal.platform.inference.notifications.events import EventType, SummaryEvent

        event = SummaryEvent(
            type=EventType.DAILY_SUMMARY,
            timestamp=datetime(2026, 3, 30, 9, 0, 0, tzinfo=UTC),
            report_date="2026-03-29",
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
        from portal.platform.inference.notifications.channels.slack import SlackChannel
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        channel = SlackChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        # Should not raise even though webhook URL is not set
        await channel.send(event)


class TestEmailChannel:
    """Email notification channel."""

    @pytest.mark.asyncio
    async def test_send_alert_skips_when_not_configured(self):
        from portal.platform.inference.notifications.channels.email import EmailChannel
        from portal.platform.inference.notifications.events import AlertEvent, EventType

        channel = EmailChannel()
        event = AlertEvent(type=EventType.BACKEND_DOWN, message="test")
        await channel.send(event)  # Should not raise


class TestNotificationDispatcher:
    """Dispatcher threshold tracking and debouncing."""

    def test_schedule_actually_runs_the_coroutine_with_no_running_loop(self):
        """Regression: `asyncio.ensure_future(coro)` does NOT raise when there
        is no running event loop -- it silently parks the coroutine on a
        fresh, never-run loop, so it never executes and the interpreter can
        exit having "scheduled" a notification that was never sent. A
        synchronous CLI script (no `asyncio.run()` anywhere) hit exactly
        this: every dispatch call "succeeded" and zero notifications were
        ever delivered. `_schedule` must actually run the coroutine to
        completion when called outside a running loop."""
        with patch.dict(os.environ, {"NOTIFICATIONS_ENABLED": "true"}):
            import importlib

            import portal.platform.inference.notifications.dispatcher as disp_mod

            importlib.reload(disp_mod)
            from portal.platform.inference.notifications.dispatcher import (
                NotificationDispatcher,
            )

            disp = NotificationDispatcher()
            ran = []

            async def coro():
                ran.append(True)

            # No event loop is running here -- this is the synchronous-script case.
            disp._schedule(coro())
            assert ran == [True], "the coroutine was scheduled but never actually run"


class TestDailySummaryDeltaComputation:
    """Verify daily summary shows deltas against previous snapshot, not cumulative totals."""

    @pytest.mark.asyncio
    async def test_summary_shows_deltas_not_cumulative_totals(self):
        """When a previous snapshot exists, the summary must show only new activity.

        Regression test: the baseline snapshot was initialized with empty counters
        because _attach_to_pipeline() was called AFTER start(). This caused every
        summary to show cumulative totals since startup instead of daily deltas.
        """
        import importlib
        import json

        import portal.platform.inference.notifications.dispatcher as disp_mod

        importlib.reload(disp_mod)
        from portal.platform.inference.notifications.dispatcher import NotificationDispatcher
        from portal.platform.inference.notifications.scheduler import NotificationScheduler

        disp = NotificationDispatcher()

        mock_backend = MagicMock()
        mock_backend.healthy = True
        mock_registry_instance = MagicMock()
        mock_registry_instance._backends = {"ollama-1": mock_backend}

        cumulative_request_count = {"auto": 1500, "auto-coding": 800}
        fake_startup = 1000000000.0

        prev_snapshot = {
            "request_count": {"auto": 1200, "auto-coding": 600},
            "total_response_time_ms": 400000.0,
            "total_tps": 8000.0,
            "request_tps_count": 400,
            "total_input_tokens": 200000,
            "total_output_tokens": 600000,
            "req_count_by_model": {
                "dolphin-llama3:8b": 1000,
                "qwen3-coder-next:30b-q5": 500,
            },
            "req_count_by_error": {"timeout": 10},
            "peak_concurrent": 5,
            "decode_tokens": 1000.0,
            "decode_seconds": 40.0,
            "answer_tokens": 100.0,
            "answer_seconds": 10.0,
            "ttft_samples": [0.2, 0.4],
            "answer_tokens_by_model": {
                "dolphin-llama3:8b": 10,
                "qwen3-coder-next:30b-q5": 5,
            },
            "answer_seconds_by_model": {
                "dolphin-llama3:8b": 1.0,
                "qwen3-coder-next:30b-q5": 1.0,
            },
        }

        current_state = {
            "request_count": {"auto": 1500, "auto-coding": 800},
            "total_response_time_ms": 450000.0,
            "total_tps": 8250.0,
            "request_tps_count": 410,
            "total_input_tokens": 210000,
            "total_output_tokens": 630000,
            "req_count_by_model": {
                "dolphin-llama3:8b": 1100,
                "qwen3-coder-next:30b-q5": 550,
                "llama3.2:3b": 50,
            },
            "req_count_by_error": {"timeout": 12, "502": 3},
            "peak_concurrent": 5,
            "persona_usage_raw": {},
            "decode_tokens": 1400.0,
            "decode_seconds": 48.0,
            "answer_tokens": 400.0,
            "answer_seconds": 20.0,
            "ttft_samples": [0.2, 0.4, 0.3, 0.5, 0.9],
            "answer_tokens_by_model": {
                "dolphin-llama3:8b": 210,
                "qwen3-coder-next:30b-q5": 105,
            },
            "answer_seconds_by_model": {
                "dolphin-llama3:8b": 5.0,
                "qwen3-coder-next:30b-q5": 6.0,
            },
        }

        from portal.platform.inference.notifications import scheduler as sched_module

        with patch.dict(os.environ, {"ALERT_SUMMARY_ENABLED": "true"}, clear=False):
            scheduler = NotificationScheduler(disp)

            sched_module._attach_to_pipeline(
                disp, cumulative_request_count, fake_startup, mock_registry_instance
            )

            snapshot_file_mock = MagicMock()
            snapshot_file_mock.exists.return_value = True
            snapshot_file_mock.read_text.return_value = json.dumps(prev_snapshot)
            snapshot_file_mock.write_text = MagicMock()

            cooldown_file_mock = MagicMock()
            cooldown_file_mock.exists.return_value = False

            with (
                patch.object(sched_module, "_load_aggregated_state", return_value=current_state),
                patch.object(sched_module, "_COOLDOWN_FILE", cooldown_file_mock),
                patch.object(sched_module, "_SNAPSHOT_FILE", snapshot_file_mock),
                patch.object(disp, "dispatch", new_callable=AsyncMock) as mock_dispatch,
            ):
                await scheduler._send_daily_summary()

            mock_dispatch.assert_called_once()
            event = mock_dispatch.call_args[0][0]

            assert event.total_requests == 500, (
                f"Expected 500 daily requests (delta), got {event.total_requests} (cumulative)"
            )
            assert event.requests_by_workspace == {"auto": 300, "auto-coding": 200}

            assert event.requests_by_model == {
                "dolphin-llama3:8b": 100,
                "qwen3-coder-next:30b-q5": 50,
                "llama3.2:3b": 50,
            }

            assert event.total_input_tokens == 10000
            assert event.total_output_tokens == 30000

            # Day is 400 decode tokens / 8s. Unweighted delta 250/10 = 25 is not the rate.
            assert event.avg_tokens_per_second == pytest.approx(50.0)
            assert event.decode_tokens_per_second == pytest.approx(50.0)
            assert event.answer_tokens_per_second == pytest.approx(30.0)
            assert event.ttft_median_seconds == pytest.approx(0.5)
            assert event.ttft_sample_count == 3
            assert event.top_models_by_volume[0] == {
                "model": "dolphin-llama3:8b",
                "answer_tokens": 200,
                "answer_tokens_per_second": pytest.approx(50.0),
            }

            assert event.avg_response_time_ms == pytest.approx(100.0)

            assert event.errors_by_type == {"timeout": 2, "502": 3}
            assert event.total_errors == 5

            snapshot_file_mock.write_text.assert_called_once()
            saved_data = json.loads(snapshot_file_mock.write_text.call_args[0][0])
            assert saved_data["request_count"] == cumulative_request_count


class TestNotificationChannelInterface:
    """Base class interface — channels must implement send_alert/send_summary."""

    def test_channel_has_name_property(self):
        from portal.platform.inference.notifications.channels import NotificationChannel

        assert hasattr(NotificationChannel, "name")
        assert hasattr(NotificationChannel, "send_alert")
        assert hasattr(NotificationChannel, "send_summary")

    def test_all_channels_registered(self):
        """Verify all available channels can be instantiated."""
        from portal.platform.inference.notifications.channels.slack import SlackChannel
        from portal.platform.inference.notifications.channels.telegram import TelegramChannel

        channels = [
            SlackChannel(),
            TelegramChannel(),
        ]
        assert all(hasattr(c, "name") for c in channels)
        names = [c.name for c in channels]
        assert "Slack" in names
        assert "Telegram" in names
