"""Unit tests for the bench_repair harness.

The tests exercise the arms end-to-end with mocked Ollama chat so they
run in <1 s and require no live model. The scoring path uses the real
capability_lib helper against a trivial in-memory problem.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.benchmarks.bench_repair import (
    ARM_ONESHOT,
    compute_gsha,
    load_corpus,
    run_one_shot,
    run_repair,
)
from tests.benchmarks.bench_repair.config import arch_from_hint

TRIVIAL_PROBLEM = {
    "id": "trivial",
    "prompt": "Write add(a, b) that returns a + b. Return in a ```python fenced block.",
    "test": (
        "from solution import add\n"
        "def test_ok():\n    assert add(2, 3) == 5\n"
        "def test_neg():\n    assert add(-1, 1) == 0\n"
    ),
}

GOOD_CODE_RESPONSE = "Sure:\n\n```python\ndef add(a, b):\n    return a + b\n```"
BROKEN_CODE_RESPONSE = "Try this:\n\n```python\ndef add(a, b):\n    return a - b\n```"
FIXED_CODE_RESPONSE = "Fixed:\n\n```python\ndef add(a, b):\n    return a + b\n```"


def test_arch_from_hint_moe_markers():
    assert arch_from_hint("qwen3.6:35b-a3b-q4_K_M") == "MoE"
    assert arch_from_hint("qwen3-coder:30b-a3b-q4_K_M") == "MoE"
    assert arch_from_hint("gemma4:26b-a4b-it-q4_K_M") == "MoE"


def test_arch_from_hint_dense():
    assert arch_from_hint("qwen3.6:27b-q4_K_M") == "dense"
    assert arch_from_hint("devstral:24b") == "dense"
    assert arch_from_hint("granite4.1:8b-ctx8k") == "dense"


def test_gsha_stable_across_calls():
    corpus = [{"id": "x", "prompt": "p", "test": "t"}]
    with patch("tests.benchmarks.bench_repair.corpus._ollama_version", return_value="0.9.9"):
        g1, _ = compute_gsha(corpus)
        g2, _ = compute_gsha(corpus)
    assert g1 == g2
    assert len(g1) == 12


def test_gsha_changes_with_corpus():
    with patch("tests.benchmarks.bench_repair.corpus._ollama_version", return_value="0.9.9"):
        g1, _ = compute_gsha([{"id": "a", "prompt": "p", "test": "t"}])
        g2, _ = compute_gsha([{"id": "a", "prompt": "p2", "test": "t"}])
    assert g1 != g2


def test_load_corpus_reads_ten_problems():
    corpus = load_corpus()
    assert len(corpus) == 10
    assert [p["id"] for p in corpus] == [f"c2_{i}" for i in range(1, 11)]


def test_one_shot_arm_records_five_samples():
    with (
        patch(
            "tests.benchmarks.bench_repair.runner._chat_ollama",
            return_value=(GOOD_CODE_RESPONSE, 0.01),
        ),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
    ):
        samples = run_one_shot("bench-fake", "fake:latest", TRIVIAL_PROBLEM)
    assert len(samples) == 5
    assert all(s.arm == ARM_ONESHOT for s in samples)
    assert all(s.passed for s in samples)


def test_repair_arm_passes_first_try_no_retry():
    call_count = {"n": 0}

    def _fake_chat(*a, **kw):
        call_count["n"] += 1
        return GOOD_CODE_RESPONSE, 0.01

    with (
        patch("tests.benchmarks.bench_repair.runner._chat_ollama", side_effect=_fake_chat),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
    ):
        samples = run_repair("bench-fake", "fake:latest", TRIVIAL_PROBLEM)
    assert len(samples) == 2
    assert all(s.detail == "pass_first_try" for s in samples)
    # First-try passes → no repair call → exactly 2 chat calls
    assert call_count["n"] == 2


def test_repair_arm_fixes_broken_first_try():
    calls: list[str] = []

    def _fake_chat(model_hint, messages, **kw):
        # First call is one-shot, second call is repair
        text = messages[0]["content"]
        if "previous attempt" in text.lower():
            calls.append("repair")
            return FIXED_CODE_RESPONSE, 0.01
        calls.append("oneshot")
        return BROKEN_CODE_RESPONSE, 0.01

    with (
        patch("tests.benchmarks.bench_repair.runner._chat_ollama", side_effect=_fake_chat),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
    ):
        samples = run_repair("bench-fake", "fake:latest", TRIVIAL_PROBLEM, n=1)
    assert len(samples) == 1
    assert samples[0].passed is True
    assert samples[0].detail == "pass_after_repair"
    assert calls == ["oneshot", "repair"]


def test_repair_arm_records_fail_after_repair():
    def _fake_chat(*a, **kw):
        return BROKEN_CODE_RESPONSE, 0.01

    with (
        patch("tests.benchmarks.bench_repair.runner._chat_ollama", side_effect=_fake_chat),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
    ):
        samples = run_repair("bench-fake", "fake:latest", TRIVIAL_PROBLEM, n=1)
    assert len(samples) == 1
    assert samples[0].passed is False
    assert samples[0].detail == "fail_after_repair"


def test_run_scenarios_survive_chat_exception():
    def _fake_chat(*a, **kw):
        raise ConnectionError("simulated ollama down")

    with (
        patch("tests.benchmarks.bench_repair.runner._chat_ollama", side_effect=_fake_chat),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
    ):
        os_samples = run_one_shot("bench-fake", "fake:latest", TRIVIAL_PROBLEM, n=2)
        rp_samples = run_repair("bench-fake", "fake:latest", TRIVIAL_PROBLEM, n=1)
    assert all(s.passed is False for s in os_samples)
    assert all(s.detail.startswith("harness_error") for s in os_samples)
    assert all(s.detail.startswith("harness_error") for s in rp_samples)
