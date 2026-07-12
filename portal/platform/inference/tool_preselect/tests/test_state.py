"""Unit tests for state.py — per-workspace auto-disable ring buffer (§5.2)."""

from __future__ import annotations

from portal.platform.inference.tool_preselect import state


class TestAutoDisable:
    def setup_method(self):
        state.reset()

    def teardown_method(self):
        state.reset()

    def test_not_disabled_initially(self):
        assert state.is_auto_disabled("ws-a") is False

    def test_under_window_size_no_disable(self):
        for _ in range(50):
            state.record_outcome("ws-b", was_miss=True)
        assert state.is_auto_disabled("ws-b") is False

    def test_low_miss_rate_no_disable(self):
        for i in range(100):
            state.record_outcome("ws-c", was_miss=(i < 3))  # 3% miss rate
        assert state.is_auto_disabled("ws-c") is False

    def test_high_miss_rate_triggers_disable(self):
        for i in range(100):
            state.record_outcome("ws-d", was_miss=(i < 10))  # 10% miss rate
        assert state.is_auto_disabled("ws-d") is True

    def test_disable_is_per_workspace(self):
        for i in range(100):
            state.record_outcome("ws-e", was_miss=(i < 10))
        assert state.is_auto_disabled("ws-e") is True
        assert state.is_auto_disabled("ws-f") is False

    def test_reset_single_workspace(self):
        for i in range(100):
            state.record_outcome("ws-g", was_miss=(i < 10))
        assert state.is_auto_disabled("ws-g") is True
        state.reset("ws-g")
        assert state.is_auto_disabled("ws-g") is False

    def test_reset_all(self):
        for i in range(100):
            state.record_outcome("ws-h", was_miss=(i < 10))
        state.reset()
        assert state.is_auto_disabled("ws-h") is False
