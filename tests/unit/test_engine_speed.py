"""Stats and verdict for the engine speed A/B. No network."""

from __future__ import annotations

from tests.benchmarks.engine_speed import (
    UNPROVEN,
    arm_stats,
    decide,
    decode_tps,
    judge_measurement,
    median,
    spread,
    summarize,
)

_EXPECT = {
    "workspace": "bench-engine-coding",
    "backend": "eval-openai-vllm-mlx",
    "model": "Qwen3.8-27B-4bit",
}


def _row(arm: str, repeat: int, rate: float, *, valid: bool = True, reason: str = "") -> dict:
    return {
        "arm": arm,
        "repeat": repeat,
        "prompt_id": f"{arm}-{repeat}",
        "valid": valid,
        "reason": reason,
        "ttft_s": 0.4,
        "decode_tps": rate,
        "total_s": 10.0 + rate / 100,
        "completion_tokens": 500,
        "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
    }


def _pair(repeat: int, cand: float, inc: float) -> list[dict]:
    return [_row("candidate", repeat, cand), _row("incumbent", repeat, inc)]


def test_decode_tps_is_completion_tokens_over_the_token_interval() -> None:
    assert decode_tps(100, 1.0, 3.0) == 50.0
    assert decode_tps(1, 1.0, 1.0) is None
    assert decode_tps(0, 0.0, 2.0) is None
    assert decode_tps(None, 0.0, 2.0) is None


def test_median_uses_the_upper_middle_and_spread_needs_two_runs() -> None:
    assert median([1.0, 4.0, 2.0, 3.0]) == 3.0
    assert median([]) is None
    assert spread([10.0, 12.0, 11.0]) == 2.0
    assert spread([10.0]) is None


def test_faster_only_when_the_median_clears_the_larger_spread() -> None:
    clear = _pair(0, 20.0, 10.0) + _pair(1, 21.0, 10.5)
    assert decide(clear)["verdict"] == "FASTER"

    tied = _pair(0, 10.0, 16.0) + _pair(1, 20.0, 16.0)
    verdict = decide(tied)
    assert verdict["verdict"] == UNPROVEN
    assert "does not exceed spread" in verdict["reason"]

    equal_noise = _pair(0, 18.0, 16.0) + _pair(1, 18.0, 16.0)
    assert decide(equal_noise)["verdict"] == "FASTER"


def test_one_repeat_cannot_clear_a_noise_floor() -> None:
    verdict = decide(_pair(0, 40.0, 10.0))
    assert verdict["verdict"] == UNPROVEN
    assert "spread is undefined" in verdict["reason"]


def test_the_floor_is_the_larger_arm_spread() -> None:
    rows = _pair(0, 20.0, 10.0) + _pair(1, 21.0, 16.0)
    stats = {arm: arm_stats(rows, arm) for arm in ("candidate", "incumbent")}
    assert stats["candidate"]["spread"] == 1.0
    assert stats["incumbent"]["spread"] == 6.0
    assert decide(rows)["verdict"] == UNPROVEN

    wider = _pair(0, 20.0, 10.0) + _pair(1, 28.0, 16.0)
    assert decide(wider)["verdict"] == "FASTER"


def test_a_route_or_request_failure_invalidates_the_comparison() -> None:
    bad = judge_measurement(
        {
            "error": None,
            "route": "bench-engine-coding;ollama;Qwen3.8-27B-4bit",
            "ttft_s": 0.2,
            "first_s": 0.2,
            "last_s": 2.2,
            "total_s": 3.0,
            "completion_tokens": 400,
            "prompt_tokens": 20,
            "http_status": 200,
        },
        _EXPECT,
    )
    assert bad["valid"] is False
    assert "pinned" in bad["reason"]

    rows = _pair(0, 30.0, 10.0) + _pair(1, 31.0, 10.0)
    rows.append(_row("candidate", 1, 0.0, valid=False, reason=bad["reason"]))
    verdict = decide(rows)
    assert verdict["verdict"] == "invalid"
    assert "pinned" in verdict["reason"]
    summary = summarize(rows)
    assert summary["arms"]["candidate"]["runs"] == 2
    assert summary["verdict"] == "invalid"


def test_missing_tokens_or_an_empty_interval_is_invalid() -> None:
    base = {
        "error": None,
        "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
        "ttft_s": 0.5,
        "first_s": 0.5,
        "last_s": 0.5,
        "total_s": 1.0,
        "completion_tokens": 40,
        "prompt_tokens": 10,
        "http_status": 200,
    }
    assert judge_measurement(base, _EXPECT)["reason"] == "decode interval is empty"
    missing = {**base, "last_s": 2.0, "completion_tokens": None, "ttft_s": None}
    assert judge_measurement(missing, _EXPECT)["reason"] == "no content or reasoning delta"
    no_usage = {**base, "last_s": 2.0, "completion_tokens": None}
    assert (
        judge_measurement(no_usage, _EXPECT)["reason"] == "engine usage missing completion_tokens"
    )


def test_a_matching_route_with_tokens_is_valid() -> None:
    row = judge_measurement(
        {
            "error": None,
            "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
            "ttft_s": 0.5,
            "first_s": 0.5,
            "last_s": 2.5,
            "total_s": 2.6,
            "completion_tokens": 100,
            "prompt_tokens": 12,
            "http_status": 200,
        },
        _EXPECT,
    )
    assert row["valid"] is True
    assert row["decode_tps"] == 50.0
