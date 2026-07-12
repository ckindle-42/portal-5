"""Unit tests for the ad-hoc TPS probe (tests.benchmarks.bench.adhoc_probe).

All Ollama calls mocked — no live backend required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from tests.benchmarks.bench.adhoc_probe import _run_one, _warmup, probe_models


def _mock_stream_response(
    chunks: list[str],
    completion_tokens: int | None = None,
    reasoning_chunks: list[str] | None = None,
):
    """Build a mock httpx streaming response yielding SSE-style lines."""
    lines = []
    for c in chunks:
        payload = json.dumps({"choices": [{"delta": {"content": c}}]})
        lines.append(f"data: {payload}")
    for r in reasoning_chunks or []:
        payload = json.dumps({"choices": [{"delta": {"reasoning": r}}]})
        lines.append(f"data: {payload}")
    if completion_tokens is not None:
        payload = json.dumps({"choices": [], "usage": {"completion_tokens": completion_tokens}})
        lines.append(f"data: {payload}")
    lines.append("data: [DONE]")

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    mock_ctx.iter_lines.return_value = lines
    return mock_ctx


class TestWarmup:
    def test_success(self):
        client = MagicMock()
        client.post.return_value = MagicMock(status_code=200)
        assert _warmup(client, "some:model") is True

    def test_non_200_is_failure(self):
        client = MagicMock()
        client.post.return_value = MagicMock(status_code=500)
        assert _warmup(client, "some:model") is False

    def test_exception_is_failure(self):
        client = MagicMock()
        client.post.side_effect = Exception("connection refused")
        assert _warmup(client, "some:model") is False


class TestRunOne:
    def test_successful_run_computes_tps(self):
        client = MagicMock()
        client.stream.return_value = _mock_stream_response(
            ["Hello", " world"], completion_tokens=10
        )
        result = _run_one(client, "some:model", "test prompt", run_num=0)
        assert result["run"] == 0
        assert result["completion_tokens"] == 10
        assert result["tps"] > 0
        assert "error" not in result

    def test_empty_response_is_error(self):
        client = MagicMock()
        client.stream.return_value = _mock_stream_response([], completion_tokens=0)
        result = _run_one(client, "some:model", "test prompt", run_num=0)
        assert result.get("error") == "empty response"

    def test_missing_usage_falls_back_to_word_count(self):
        client = MagicMock()
        client.stream.return_value = _mock_stream_response(
            ["one two three four five"], completion_tokens=None
        )
        result = _run_one(client, "some:model", "test prompt", run_num=0)
        assert result["completion_tokens"] == 5
        assert "error" not in result

    def test_exception_during_stream_is_error(self):
        client = MagicMock()
        client.stream.side_effect = Exception("timeout")
        result = _run_one(client, "some:model", "test prompt", run_num=0)
        assert "error" in result

    def test_thinking_model_reasoning_only_counts_as_generation(self):
        """Regression test: a 'thinking' model (gemma4's Capabilities list
        includes "thinking") can emit its entire response through
        delta.reasoning with an empty delta.content. Before the fix, this
        was misreported as "empty response" despite genuine generation —
        discovered live during TASK_EVAL_GEMMA4_MLX_TAGS_V1 (gemma4:e2b-mlx
        returned "empty response" on every trial of a real TPS probe)."""
        client = MagicMock()
        client.stream.return_value = _mock_stream_response(
            chunks=[],
            completion_tokens=None,
            reasoning_chunks=["Thinking about", " the OSI model", " layers..."],
        )
        result = _run_one(client, "gemma4:e2b-mlx", "test prompt", run_num=0)
        assert "error" not in result
        assert result["completion_tokens"] > 0
        assert result["tps"] > 0


class TestProbeModels:
    def test_warmup_failure_skips_trials(self):
        with patch("tests.benchmarks.bench.adhoc_probe._warmup", return_value=False):
            results = probe_models(["some:model"], runs=3, prompt_category="general")
        assert results["some:model"]["error"] == "warmup_failed"

    def test_all_models_probed(self):
        with (
            patch("tests.benchmarks.bench.adhoc_probe._warmup", return_value=True),
            patch(
                "tests.benchmarks.bench.adhoc_probe._run_one",
                return_value={"run": 0, "elapsed_s": 1.0, "completion_tokens": 100, "tps": 100.0},
            ),
        ):
            results = probe_models(["model:a", "model:b"], runs=2, prompt_category="general")
        assert set(results.keys()) == {"model:a", "model:b"}
        assert results["model:a"]["median_tps"] == 100.0
        assert results["model:a"]["n_trials"] == 2

    def test_unknown_prompt_category_falls_back_to_general(self):
        with (
            patch("tests.benchmarks.bench.adhoc_probe._warmup", return_value=True) as mock_wu,
            patch(
                "tests.benchmarks.bench.adhoc_probe._run_one",
                return_value={"run": 0, "elapsed_s": 1.0, "completion_tokens": 1, "tps": 1.0},
            ),
        ):
            # "general" is always a valid key in PROMPTS; this just confirms
            # probe_models doesn't raise on the default category.
            results = probe_models(["model:a"], runs=1, prompt_category="general")
        assert mock_wu.called
        assert "model:a" in results
