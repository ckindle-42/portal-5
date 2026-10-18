"""Token-weighted decode, answer, and TTFT metrics.

The deprecated ``portal_tokens_per_second`` histogram still falls back to wall
clock. The new series do not: a request with tokens but no decode time is
counted on ``portal_tps_unmeasured_total`` and left out of the ratio.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import portal.platform.inference.router.state as state
from portal.platform.inference.notifications.scheduler import (
    _delta_samples,
    _median,
    _top_models_by_answer_volume,
    _weighted_rate,
)
from portal.platform.inference.router.metrics import (
    _REGISTRY,
    _answer_seconds,
    _answer_tokens,
    _decode_seconds,
    _decode_tokens,
    _tokens_per_second,
    _tps_unmeasured,
    _ttft_seconds,
)
from portal.platform.inference.router.power import _record_usage

_DASHBOARD = Path("config/grafana/dashboards/portal5_overview.json")


def _counter(metric, **labels) -> float:
    return float(metric.labels(**labels)._value.get())


def _hist_sum(metric, **labels) -> float:
    return float(metric.labels(**labels)._sum.get())


@pytest.fixture
def _restore_digest_state():
    saved = (
        state._decode_tokens,
        state._decode_seconds,
        state._answer_tokens,
        state._answer_seconds,
        list(state._ttft_samples),
        dict(state._answer_tokens_by_model),
        dict(state._answer_seconds_by_model),
    )
    yield
    (
        state._decode_tokens,
        state._decode_seconds,
        state._answer_tokens,
        state._answer_seconds,
        state._ttft_samples,
        tokens_by_model,
        seconds_by_model,
    ) = saved
    state._answer_tokens_by_model.clear()
    state._answer_tokens_by_model.update(tokens_by_model)
    state._answer_seconds_by_model.clear()
    state._answer_seconds_by_model.update(seconds_by_model)


@pytest.mark.usefixtures("_restore_digest_state")
class TestRecordTimingSeries:
    def test_engine_eval_duration_is_decode_time(self):
        """Ollama eval_count / eval_duration feeds the decode counters, not wall clock."""
        model, workspace = "tps-engine-model", "tps-engine-ws"
        before_tokens = _counter(_decode_tokens, model=model, workspace=workspace, source="engine")
        before_seconds = _counter(
            _decode_seconds, model=model, workspace=workspace, source="engine"
        )
        before_measured = _counter(
            _decode_seconds, model=model, workspace=workspace, source="measured"
        )
        before_unmeasured = _counter(_tps_unmeasured, model=model, workspace=workspace)
        before_hist = _hist_sum(_tokens_per_second, model=model, workspace=workspace)
        before_answer = _counter(
            _answer_tokens, model=model, workspace=workspace, source="measured"
        )

        _record_usage(
            model=model,
            workspace=workspace,
            data={"eval_count": 100, "eval_duration": 2_000_000_000, "prompt_eval_count": 20},
            elapsed_seconds=50.0,
            decode_seconds=9.0,
        )

        assert _counter(
            _decode_tokens, model=model, workspace=workspace, source="engine"
        ) - before_tokens == pytest.approx(100)
        assert _counter(
            _decode_seconds, model=model, workspace=workspace, source="engine"
        ) - before_seconds == pytest.approx(2.0)
        assert (
            _counter(_decode_seconds, model=model, workspace=workspace, source="measured")
            == before_measured
        )
        assert _counter(_tps_unmeasured, model=model, workspace=workspace) == before_unmeasured
        assert _hist_sum(_tokens_per_second, model=model, workspace=workspace) - before_hist == (
            pytest.approx(50.0)
        )
        assert (
            _counter(_answer_tokens, model=model, workspace=workspace, source="measured")
            == before_answer
        )

    def test_measured_kwargs_do_not_use_wall_clock(self):
        """Caller decode/answer/TTFT timings record; elapsed_seconds stays on the old histogram."""
        model, workspace = "tps-measured-model", "tps-measured-ws"
        before_tokens = _counter(
            _decode_tokens, model=model, workspace=workspace, source="measured"
        )
        before_seconds = _counter(
            _decode_seconds, model=model, workspace=workspace, source="measured"
        )
        before_answer_tokens = _counter(
            _answer_tokens, model=model, workspace=workspace, source="measured"
        )
        before_answer_seconds = _counter(
            _answer_seconds, model=model, workspace=workspace, source="measured"
        )
        before_ttft = _hist_sum(_ttft_seconds, model=model, workspace=workspace, source="measured")
        before_unmeasured = _counter(_tps_unmeasured, model=model, workspace=workspace)
        before_hist = _hist_sum(_tokens_per_second, model=model, workspace=workspace)

        _record_usage(
            model=model,
            workspace=workspace,
            data={"completion_tokens": 100, "prompt_tokens": 12},
            elapsed_seconds=50.0,
            decode_seconds=2.0,
            ttft_seconds=0.4,
            reasoning_tokens=40,
            answer_seconds=1.2,
            answer_tokens=60,
        )

        assert _counter(
            _decode_tokens, model=model, workspace=workspace, source="measured"
        ) - before_tokens == pytest.approx(100)
        assert _counter(
            _decode_seconds, model=model, workspace=workspace, source="measured"
        ) - before_seconds == pytest.approx(2.0)
        assert _counter(
            _answer_tokens, model=model, workspace=workspace, source="measured"
        ) - before_answer_tokens == pytest.approx(60)
        assert _counter(
            _answer_seconds, model=model, workspace=workspace, source="measured"
        ) - before_answer_seconds == pytest.approx(1.2)
        assert _hist_sum(
            _ttft_seconds, model=model, workspace=workspace, source="measured"
        ) - before_ttft == pytest.approx(0.4)
        assert _counter(_tps_unmeasured, model=model, workspace=workspace) == before_unmeasured
        # Deprecated histogram: 100 completion tokens / 50s wall clock.
        assert _hist_sum(_tokens_per_second, model=model, workspace=workspace) - before_hist == (
            pytest.approx(2.0)
        )

    def test_answer_tokens_default_to_completion_minus_reasoning(self):
        model, workspace = "tps-split-model", "tps-split-ws"
        before = _counter(_answer_tokens, model=model, workspace=workspace, source="measured")

        _record_usage(
            model=model,
            workspace=workspace,
            data={"completion_tokens": 100},
            decode_seconds=2.0,
            reasoning_tokens=30,
            answer_seconds=1.5,
        )

        assert _counter(
            _answer_tokens, model=model, workspace=workspace, source="measured"
        ) - before == pytest.approx(70)

    def test_absent_decode_time_is_unmeasured_not_wall_clock(self):
        model, workspace = "tps-unmeasured-model", "tps-unmeasured-ws"
        before_tokens = _counter(_decode_tokens, model=model, workspace=workspace, source="engine")
        before_measured = _counter(
            _decode_tokens, model=model, workspace=workspace, source="measured"
        )
        before_unmeasured = _counter(_tps_unmeasured, model=model, workspace=workspace)
        before_hist = _hist_sum(_tokens_per_second, model=model, workspace=workspace)
        before_answer = _counter(
            _answer_tokens, model=model, workspace=workspace, source="measured"
        )
        before_ttft = _hist_sum(_ttft_seconds, model=model, workspace=workspace, source="measured")

        _record_usage(
            model=model,
            workspace=workspace,
            data={"completion_tokens": 80},
            elapsed_seconds=4.0,
            ttft_seconds=0.25,
        )

        assert _counter(_decode_tokens, model=model, workspace=workspace, source="engine") == (
            before_tokens
        )
        assert (
            _counter(_decode_tokens, model=model, workspace=workspace, source="measured")
            == before_measured
        )
        assert _counter(_tps_unmeasured, model=model, workspace=workspace) - before_unmeasured == (
            pytest.approx(1)
        )
        assert _hist_sum(_tokens_per_second, model=model, workspace=workspace) - before_hist == (
            pytest.approx(20.0)
        )
        assert (
            _counter(_answer_tokens, model=model, workspace=workspace, source="measured")
            == before_answer
        )
        assert _hist_sum(
            _ttft_seconds, model=model, workspace=workspace, source="measured"
        ) - before_ttft == pytest.approx(0.25)

    def test_no_tokens_does_not_count_as_unmeasured(self):
        model, workspace = "tps-empty-model", "tps-empty-ws"
        before = _counter(_tps_unmeasured, model=model, workspace=workspace)

        _record_usage(model=model, workspace=workspace, data={}, elapsed_seconds=4.0)

        assert _counter(_tps_unmeasured, model=model, workspace=workspace) == before

    def test_new_timings_are_keyword_only(self):
        with pytest.raises(TypeError):
            _record_usage("m", "w", {"completion_tokens": 1}, 1.0, 2.0)  # type: ignore[misc]

    def test_bench_workspace_skips_digest_accumulators(self):
        model, workspace = "tps-bench-model", "bench-speed"
        before_prom = _counter(_decode_tokens, model=model, workspace=workspace, source="engine")
        before_digest = state._decode_tokens
        before_ttft = len(state._ttft_samples)
        before_answer = state._answer_tokens

        _record_usage(
            model=model,
            workspace=workspace,
            data={"eval_count": 40, "eval_duration": 1_000_000_000},
            ttft_seconds=0.2,
            reasoning_tokens=10,
            answer_seconds=0.5,
            answer_tokens=30,
        )

        assert _counter(
            _decode_tokens, model=model, workspace=workspace, source="engine"
        ) - before_prom == pytest.approx(40)
        assert state._decode_tokens == before_digest
        assert len(state._ttft_samples) == before_ttft
        assert state._answer_tokens == before_answer

    def test_non_bench_updates_digest_accumulators(self):
        model, workspace = "tps-digest-model", "tps-digest-ws"
        before_tokens = state._decode_tokens
        before_seconds = state._decode_seconds
        before_answer = state._answer_tokens
        before_samples = len(state._ttft_samples)

        _record_usage(
            model=model,
            workspace=workspace,
            data={"completion_tokens": 50},
            decode_seconds=2.0,
            ttft_seconds=0.3,
            answer_tokens=50,
            answer_seconds=2.0,
        )

        assert state._decode_tokens - before_tokens == pytest.approx(50)
        assert state._decode_seconds - before_seconds == pytest.approx(2.0)
        assert state._answer_tokens - before_answer == pytest.approx(50)
        assert len(state._ttft_samples) == before_samples + 1
        assert state._answer_tokens_by_model[model] >= 50

    def test_exposition_names_the_series_and_marks_the_histogram_deprecated(self):
        from prometheus_client import generate_latest

        text = generate_latest(_REGISTRY).decode()
        for name in (
            "portal_decode_tokens_total",
            "portal_decode_seconds_total",
            "portal_answer_tokens_total",
            "portal_answer_seconds_total",
            "portal_ttft_seconds",
            "portal_tps_unmeasured_total",
            "portal_tokens_per_second",
        ):
            assert name in text
        assert "DEPRECATED" in text


class TestDigestMath:
    def test_weighted_rate_and_median(self):
        assert _weighted_rate(300, 10) == pytest.approx(30)
        assert _weighted_rate(10, 0) == 0.0
        assert _median([]) == 0.0
        assert _median([0.2, 0.9, 0.4]) == pytest.approx(0.4)
        assert _median([0.2, 0.4, 0.5, 1.1]) == pytest.approx(0.45)

    def test_sample_delta_uses_the_appended_tail(self):
        assert _delta_samples([0.1, 0.2, 0.3], [0.1, 0.2]) == [0.3]
        assert _delta_samples([0.9], [0.1, 0.2]) == [0.9]
        assert _delta_samples([], [0.1]) == []

    def test_top_models_rank_by_answer_tokens(self):
        rows = _top_models_by_answer_volume(
            {"slow": 10, "fast": 100},
            {"slow": 10.0, "fast": 2.0},
        )
        assert rows[0]["model"] == "fast"
        assert rows[0]["answer_tokens"] == 100
        assert rows[0]["answer_tokens_per_second"] == pytest.approx(50)


class TestOverviewDashboard:
    def test_tps_panels_are_windowed_ratios(self):
        dashboard = json.loads(_DASHBOARD.read_text())
        exprs: list[str] = []
        titles: list[str] = []
        for panel in dashboard["panels"]:
            titles.append(panel.get("title", ""))
            for target in panel.get("targets") or []:
                expr = target.get("expr")
                if isinstance(expr, str):
                    exprs.append(expr)

        joined = "\n".join(exprs)
        assert "portal_tokens_per_second" not in joined
        assert "Avg Tokens/sec (Aggregate)" not in titles
        assert (
            "sum by(model) (rate(portal_decode_tokens_total[5m])) "
            "/ sum by(model) (rate(portal_decode_seconds_total[5m]))"
        ) in exprs
        assert (
            "sum by(model) (rate(portal_answer_tokens_total[5m])) "
            "/ sum by(model) (rate(portal_answer_seconds_total[5m]))"
        ) in exprs
        assert (
            "sum by(workspace) (rate(portal_decode_tokens_total[5m])) "
            "/ sum by(workspace) (rate(portal_decode_seconds_total[5m]))"
        ) in exprs
        assert (
            "sum by(workspace) (rate(portal_answer_tokens_total[5m])) "
            "/ sum by(workspace) (rate(portal_answer_seconds_total[5m]))"
        ) in exprs
        assert (
            "histogram_quantile(0.50, sum by(model, le) (rate(portal_ttft_seconds_bucket[5m])))"
        ) in exprs
        assert (
            "histogram_quantile(0.90, sum by(model, le) (rate(portal_ttft_seconds_bucket[5m])))"
        ) in exprs
        speed = [expr for expr in exprs if "portal_decode_" in expr or "portal_answer_" in expr]
        assert speed
        assert all("rate(" in expr for expr in speed)
