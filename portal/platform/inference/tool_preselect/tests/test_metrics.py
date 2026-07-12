"""Unit tests for metrics.py — record_* helpers never raise, update collectors."""

from __future__ import annotations

from dataclasses import dataclass

from portal.platform.inference.router.metrics import (
    toolpreselect_auto_disabled_total,
    toolpreselect_calls_total,
    toolpreselect_miss_total,
)
from portal.platform.inference.tool_preselect.metrics import (
    record_auto_disabled,
    record_miss,
    record_preselect_call,
)


@dataclass
class _FakeOutcome:
    reason: str
    latency_ms: int


class TestRecordPreselectCall:
    def test_ok_outcome_increments_counter(self):
        before = toolpreselect_calls_total.labels(workspace="ws-m1", outcome="ok")._value.get()
        record_preselect_call("ws-m1", _FakeOutcome("ok", 42), tools_available=10, tools_selected=3)
        after = toolpreselect_calls_total.labels(workspace="ws-m1", outcome="ok")._value.get()
        assert after == before + 1

    def test_fallback_outcome_does_not_raise(self):
        record_preselect_call(
            "ws-m2", _FakeOutcome("fallback_timeout", 2000), tools_available=10, tools_selected=10
        )

    def test_never_raises_on_malformed_outcome(self):
        # outcome missing .reason/.latency_ms entirely — getattr fallbacks handle it
        record_preselect_call("ws-m3", object(), tools_available=10, tools_selected=3)


class TestRecordMiss:
    def test_increments_counter(self):
        before = toolpreselect_miss_total.labels(workspace="ws-miss")._value.get()
        record_miss("ws-miss")
        after = toolpreselect_miss_total.labels(workspace="ws-miss")._value.get()
        assert after == before + 1


class TestRecordAutoDisabled:
    def test_increments_counter(self):
        before = toolpreselect_auto_disabled_total.labels(workspace="ws-ad")._value.get()
        record_auto_disabled("ws-ad")
        after = toolpreselect_auto_disabled_total.labels(workspace="ws-ad")._value.get()
        assert after == before + 1
