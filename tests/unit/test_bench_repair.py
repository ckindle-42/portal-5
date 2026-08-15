"""Unit tests for the bench_repair harness.

The tests exercise the arms end-to-end with mocked Ollama chat so they
run in <1 s and require no live model. The scoring path uses the real
capability_lib helper against a trivial in-memory problem.
"""

from __future__ import annotations

from unittest.mock import patch

from tests.benchmarks.bench_repair import (
    ARM_ONESHOT,
    ARM_REPAIR,
    append_samples,
    cell_done,
    checkpoint_path,
    compute_gsha,
    load_checkpoint,
    load_corpus,
    run_one_shot,
    run_repair,
    samples_for_cell,
)
from tests.benchmarks.bench_repair.cli import (
    _omlx_alias_group,
    _resolve_workspace,
    _run_all_workspaces,
)
from tests.benchmarks.bench_repair.config import arch_from_hint
from tests.benchmarks.bench_repair.runner import SampleResult, _chat_ollama

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


def _sample(ws="bench-fake", pid="c2_1", arm=ARM_ONESHOT, idx=0, passed=True):
    return SampleResult(
        workspace=ws,
        model_hint="fake:latest",
        arm=arm,
        problem_id=pid,
        sample_idx=idx,
        passed=passed,
        detail="pass",
        latency_s=0.01,
    )


def test_checkpoint_roundtrip(tmp_path):
    path = checkpoint_path(tmp_path, "gsha123")
    assert load_checkpoint(path) == []
    append_samples(path, "gsha123", [_sample(idx=0), _sample(idx=1)])
    append_samples(path, "gsha123", [_sample(idx=2)])
    loaded = load_checkpoint(path)
    assert len(loaded) == 3
    assert [s.sample_idx for s in loaded] == [0, 1, 2]


def test_load_checkpoint_missing_file_returns_empty(tmp_path):
    assert load_checkpoint(tmp_path / "does_not_exist.json") == []


def test_cell_done_and_samples_for_cell():
    samples = [_sample(idx=0), _sample(idx=1), _sample(pid="c2_2", idx=0)]
    assert cell_done(samples, "bench-fake", "c2_1", ARM_ONESHOT, n=2) is True
    assert cell_done(samples, "bench-fake", "c2_1", ARM_ONESHOT, n=3) is False
    assert cell_done(samples, "bench-fake", "c2_1", ARM_REPAIR, n=1) is False
    assert len(samples_for_cell(samples, "bench-fake", "c2_1", ARM_ONESHOT)) == 2


def test_resume_skips_completed_cells_without_calling_ollama(tmp_path):
    corpus = [TRIVIAL_PROBLEM]
    ckpt = checkpoint_path(tmp_path, "gsha_resume")
    call_count = {"n": 0}

    def _fake_chat(*a, **kw):
        call_count["n"] += 1
        return GOOD_CODE_RESPONSE, 0.01

    with (
        patch("tests.benchmarks.bench_repair.runner._chat_ollama", side_effect=_fake_chat),
        patch("tests.benchmarks.bench_repair.runner._emits_reasoning", return_value=False),
        patch("tests.benchmarks.bench_repair.cli.evict_all"),
    ):
        resolved = {"bench-fake": {"model_hint": "fake:latest", "sampling": {}, "think": None}}
        first = _run_all_workspaces(
            ["bench-fake"],
            resolved,
            corpus,
            ckpt_path=ckpt,
            gsha="gsha_resume",
        )
        first_calls = call_count["n"]
        assert first_calls > 0
        assert len(first) == 5 + 2  # one-shot n=5 + repair n=2

        second = _run_all_workspaces(
            ["bench-fake"],
            resolved,
            corpus,
            ckpt_path=ckpt,
            gsha="gsha_resume",
        )
    # Second call resumes entirely from checkpoint — no new Ollama calls.
    assert call_count["n"] == first_calls
    assert len(second) == len(first)


class _FakeHttpxResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_chat_ollama_sends_full_sampling_via_native_options(monkeypatch):
    captured = {}

    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _FakeHttpxResponse({"message": {"content": "hi"}})

    monkeypatch.setattr("tests.benchmarks.bench_repair.runner.httpx.post", _fake_post)
    content, _elapsed = _chat_ollama(
        "some-model",
        [{"role": "user", "content": "x"}],
        token_budget=1234,
        sampling={
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "min_p": 0.0,
            "repeat_penalty": 1.0,
            "presence_penalty": 1.5,
            "seed": 42,
        },
        think=False,
    )
    assert content == "hi"
    assert captured["url"].endswith("/api/chat")
    body = captured["json"]
    assert "options" in body and "choices" not in body  # not the OpenAI-compat shape
    opts = body["options"]
    assert opts["num_predict"] == 1234
    assert opts["temperature"] == 0.7
    assert opts["top_p"] == 0.8
    assert opts["top_k"] == 20
    assert opts["min_p"] == 0.0
    assert opts["repeat_penalty"] == 1.0
    assert opts["presence_penalty"] == 1.5
    assert opts["seed"] == 42
    assert body["think"] is False


def test_chat_ollama_omits_unset_sampling_and_think(monkeypatch):
    captured = {}

    def _fake_post(url, json, timeout):
        captured["json"] = json
        return _FakeHttpxResponse({"message": {"content": ""}})

    monkeypatch.setattr("tests.benchmarks.bench_repair.runner.httpx.post", _fake_post)
    _chat_ollama("some-model", [{"role": "user", "content": "x"}], token_budget=100)
    body = captured["json"]
    assert body["options"] == {"num_predict": 100}
    assert "think" not in body


def test_resolve_workspace_skips_missing_workspace(capsys):
    assert _resolve_workspace("bench-this-workspace-does-not-exist") is None
    assert "WARNING" in capsys.readouterr().err


def test_resolve_workspace_returns_model_hint_and_sampling():
    r = _resolve_workspace("bench-qwen38-27b")
    assert r is not None
    assert r["model_hint"] == "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M"
    assert isinstance(r["sampling"], dict)


def test_omlx_alias_group_none_for_non_aliased_model():
    assert _omlx_alias_group("this-model-id-is-not-aliased-anywhere") is None
