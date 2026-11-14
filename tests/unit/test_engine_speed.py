"""Stats and verdict for the engine speed A/B. No network."""

from __future__ import annotations

from tests.benchmarks import engine_speed as speed
from tests.benchmarks.engine_speed import (
    UNPROVEN,
    arm_stats,
    decide,
    decode_tps,
    judge_measurement,
    judge_warmup,
    median,
    spread,
    summarize,
    warmup_body,
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


def _measured(
    *,
    chunks: int,
    ttft: float,
    first: float,
    last: float,
    total: float,
    tokens: int,
) -> dict:
    return {
        "error": None,
        "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
        "ttft_s": ttft,
        "first_s": first,
        "last_s": last,
        "total_s": total,
        "completion_tokens": tokens,
        "prompt_tokens": 10,
        "http_status": 200,
        "content_chunks": chunks,
    }


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
        "content_chunks": 5,
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
    assert row["streaming"] is True


def test_two_or_fewer_chunks_record_throughput_not_decode() -> None:
    burst = judge_measurement(
        _measured(chunks=1, ttft=10.0, first=10.0, last=10.0, total=10.5, tokens=800),
        _EXPECT,
    )
    assert burst["valid"] is True
    assert burst["streaming"] is False
    assert burst["decode_tps"] is None
    assert burst["throughput_tok_s"] == 1600.0
    assert burst["e2e_tok_s"] == 800 / 10.5
    assert burst["reason"] != "decode interval is empty"

    flat = judge_measurement(
        _measured(chunks=2, ttft=4.0, first=4.0, last=4.0, total=4.0, tokens=80),
        _EXPECT,
    )
    assert flat["streaming"] is False
    assert flat["throughput_tok_s"] == 20.0

    streamed = judge_measurement(
        _measured(chunks=3, ttft=0.5, first=0.5, last=2.5, total=2.6, tokens=100),
        _EXPECT,
    )
    assert streamed["streaming"] is True
    assert streamed["decode_tps"] == 50.0
    assert streamed["throughput_tok_s"] is None


def test_a_burst_compares_end_to_end_throughput_for_both_arms() -> None:
    rows: list[dict] = []
    for repeat, cand_e2e in ((0, 50.0), (1, 51.0)):
        rows.append(
            {
                **_row("candidate", repeat, 0.0),
                "streaming": False,
                "decode_tps": None,
                "throughput_tok_s": 100000.0,
                "e2e_tok_s": cand_e2e,
            }
        )
        rows.append({**_row("incumbent", repeat, 100.0), "streaming": True, "e2e_tok_s": 20.0})
    verdict = decide(rows)
    assert verdict["metric"] == "e2e_tok_s"
    assert verdict["verdict"] == "FASTER"
    assert "did not stream" in verdict["reason"]
    assert "end-to-end" in verdict["reason"]

    one = [
        {
            **_row("candidate", 0, 1.0),
            "streaming": False,
            "decode_tps": None,
            "throughput_tok_s": 1000.0,
            "e2e_tok_s": 40.0,
        },
        {**_row("incumbent", 0, 100.0), "streaming": True, "e2e_tok_s": 10.0},
    ]
    unproven = decide(one)
    assert unproven["verdict"] == UNPROVEN
    assert unproven["metric"] == "e2e_tok_s"
    assert "spread is undefined" in unproven["reason"]
    assert "end-to-end" in unproven["reason"]


def test_both_streaming_arms_keep_the_decode_comparison() -> None:
    rows: list[dict] = []
    for repeat, cand, inc in ((0, 20.0, 10.0), (1, 21.0, 10.5)):
        rows.append({**_row("candidate", repeat, cand), "streaming": True, "e2e_tok_s": 5.0})
        rows.append({**_row("incumbent", repeat, inc), "streaming": True, "e2e_tok_s": 40.0})
    verdict = decide(rows)
    assert verdict["metric"] == "decode_tps"
    assert verdict["verdict"] == "FASTER"
    assert "end-to-end" not in verdict["reason"]


def test_warmup_is_short_same_seat_and_timed_separately(monkeypatch) -> None:
    body = warmup_body("bench-engine-coding", "eval-openai-vllm-mlx")
    assert body["model"] == "bench-engine-coding"
    assert body["portal_backend"] == "eval-openai-vllm-mlx"
    assert body["max_tokens"] == 16
    assert body["messages"][0]["content"] == "Reply with ok."
    failed = judge_warmup(
        {
            "error": "HTTP 500: down",
            "route": "",
            "http_status": 500,
            "total_s": None,
            "ttft_s": None,
            "completion_tokens": None,
        },
        _EXPECT,
    )
    assert failed["warmup_s"] is None
    assert failed["error"] == "HTTP 500: down"

    calls: list[int] = []

    def fake_stream(_pipeline: str, body: dict, _timeout_s: float = 1800.0) -> dict:
        calls.append(int(body["max_tokens"]))
        short = body["max_tokens"] == 16
        return {
            "error": None,
            "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
            "http_status": 200,
            "ttft_s": 0.2,
            "first_s": 0.2,
            "last_s": 0.4 if short else 1.2,
            "total_s": 0.5 if short else 9.0,
            "completion_tokens": 4 if short else 100,
            "prompt_tokens": 3,
            "content_chunks": 1 if short else 4,
        }

    def ready(*_args: object, **_kwargs: object) -> dict:
        return {"backend": {}}

    monkeypatch.setattr(speed.runner, "wait_pipeline_eval_backend", ready)
    monkeypatch.setattr(speed, "_resident", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(speed, "stream_once", fake_stream)
    record: dict = {}
    speed._measure_loaded(
        {},
        "http://127.0.0.1:9099",
        _EXPECT,
        [{"id": "coding-01", "text": "timed prompt"}],
        "incumbent",
        0,
        record,
    )
    assert calls == [16, 800]
    assert record["warmup"]["warmup_s"] == 0.5
    assert record["warmup"]["error"] is None
    assert [row["prompt_id"] for row in record["rows"]] == ["coding-01"]
    assert record["rows"][0]["total_s"] == 9.0
    assert record["rows"][0]["ttft_s"] == 0.2


def test_a_failed_warmup_is_not_a_timed_row(monkeypatch) -> None:
    calls: list[int] = []

    def fake_stream(_pipeline: str, body: dict, _timeout_s: float = 1800.0) -> dict:
        calls.append(int(body["max_tokens"]))
        return {
            "error": "HTTP 500: down",
            "route": "",
            "http_status": 500,
            "ttft_s": None,
            "first_s": None,
            "last_s": None,
            "total_s": None,
            "completion_tokens": None,
            "prompt_tokens": None,
            "content_chunks": 0,
        }

    def ready(*_args: object, **_kwargs: object) -> dict:
        return {"backend": {}}

    monkeypatch.setattr(speed.runner, "wait_pipeline_eval_backend", ready)
    monkeypatch.setattr(speed, "_resident", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(speed, "stream_once", fake_stream)
    record: dict = {}
    speed._measure_loaded(
        {},
        "http://127.0.0.1:9099",
        _EXPECT,
        [{"id": "coding-01", "text": "timed prompt"}],
        "candidate",
        0,
        record,
    )
    assert calls == [16]
    assert record["rows"][0]["prompt_id"] == "warmup"
    assert record["rows"][0]["valid"] is False
    assert str(record["rows"][0]["reason"]).startswith("warm-up failed:")
