"""Stats and verdict for the engine speed A/B. No network."""

from __future__ import annotations

import json

from tests.benchmarks import engine_speed as speed
from tests.benchmarks.engine_speed import (
    UNPROVEN,
    append_summary_row,
    arm_stats,
    candidate_cell,
    decide,
    decode_tps,
    format_invalid,
    format_table,
    judge_measurement,
    judge_warmup,
    load_prompts,
    median,
    parse_args,
    select_canary_cells,
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


def test_a_route_failure_invalidates_only_rows_below_the_coverage_floor() -> None:
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

    rows = [
        _row(arm, repeat, rate)
        for repeat in range(5)
        for _ in range(2)
        for arm, rate in (("candidate", 30.0 + repeat), ("incumbent", 10.0 + repeat))
    ]
    rows[0] = {
        **bad,
        "arm": "candidate",
        "repeat": 0,
        "prompt_id": "candidate-0-bad-route",
    }
    verdict = decide(rows)
    assert verdict["verdict"] == "FASTER"
    assert "pinned" in format_invalid(rows)
    summary = summarize(rows)
    assert summary["arms"]["candidate"]["runs"] == 9
    assert summary["verdict"] == "FASTER"


def test_less_than_eighty_percent_valid_rows_invalidates_the_verdict() -> None:
    rows = [
        _row(arm, repeat, rate)
        for repeat in range(5)
        for _ in range(2)
        for arm, rate in (("candidate", 30.0 + repeat), ("incumbent", 10.0 + repeat))
    ]
    for row in [item for item in rows if item["arm"] == "candidate"][:3]:
        row.update(valid=False, reason="engine usage missing completion_tokens")
    verdict = decide(rows)
    assert verdict["verdict"] == "invalid"
    assert "candidate valid rows 7/10" in verdict["reason"]


def test_missing_engine_usage_is_a_row_failure_not_a_pair_failure() -> None:
    missing_usage = judge_measurement(
        {
            "error": None,
            "route": "bench-engine-coding;eval-openai-vllm-mlx;Qwen3.8-27B-4bit",
            "ttft_s": 0.4,
            "first_s": 0.4,
            "last_s": 1.4,
            "total_s": 1.5,
            "completion_tokens": None,
            "prompt_tokens": 20,
            "http_status": 200,
            "content_chunks": 4,
        },
        _EXPECT,
    )
    assert missing_usage["reason"] == "engine usage missing completion_tokens"
    rows = [
        _row(arm, repeat, rate)
        for repeat in range(5)
        for _ in range(2)
        for arm, rate in (("candidate", 30.0 + repeat), ("incumbent", 10.0 + repeat))
    ]
    rows[0] = {**missing_usage, "arm": "candidate", "repeat": 0, "prompt_id": "no-usage"}
    assert decide(rows)["verdict"] == "FASTER"
    assert "no-usage | engine usage missing completion_tokens" in format_invalid(rows)


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
    assert burst["throughput_tok_s"] is None
    assert burst["e2e_tok_s"] == 800 / 10.5
    assert burst["reason"] != "decode interval is empty"

    flat = judge_measurement(
        _measured(chunks=2, ttft=4.0, first=4.0, last=4.0, total=4.0, tokens=80),
        _EXPECT,
    )
    assert flat["streaming"] is False
    assert flat["throughput_tok_s"] is None
    assert flat["e2e_tok_s"] == 20.0

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
                "throughput_tok_s": None,
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
            "throughput_tok_s": None,
            "e2e_tok_s": 40.0,
        },
        {**_row("incumbent", 0, 100.0), "streaming": True, "e2e_tok_s": 10.0},
    ]
    unproven = decide(one)
    assert unproven["verdict"] == UNPROVEN
    assert unproven["metric"] == "e2e_tok_s"
    assert "spread is undefined" in unproven["reason"]
    assert "end-to-end" in unproven["reason"]


def test_non_streaming_table_only_displays_end_to_end_rate() -> None:
    rows = []
    for repeat in range(2):
        for arm, rate in (("candidate", 40.0 + repeat), ("incumbent", 20.0 + repeat)):
            rows.append(
                {
                    **_row(arm, repeat, 0.0),
                    "streaming": False,
                    "decode_tps": None,
                    "throughput_tok_s": None,
                    "e2e_tok_s": rate,
                }
            )
    table = format_table(summarize(rows))
    assert "median e2e tok/s" in table
    assert "median decode tok/s" not in table
    assert "throughput tok/s" not in table


def test_burst_row_prints_only_end_to_end_rate(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        speed,
        "stream_once",
        lambda *_args, **_kwargs: _measured(
            chunks=1, ttft=2.0, first=2.0, last=2.0, total=2.0001, tokens=800
        ),
    )
    row = speed.one_request(
        "http://pipeline",
        _EXPECT,
        {"id": "coding-01", "text": "prompt"},
        "candidate",
        0,
    )
    output = capsys.readouterr().out
    assert row["throughput_tok_s"] is None
    assert row["e2e_tok_s"] == 800 / 2.0001
    assert "e2e=" in output
    assert "decode=" not in output
    assert "throughput" not in output


def test_candidate_cell_uses_requested_seat_engine_and_mode(monkeypatch) -> None:
    cell = {
        "seat": "hunt",
        "engine": "rapid-mlx",
        "mode": "plain",
        "workspace": "bench-engine-hunt",
        "model": "gemma4_26b_a4b_qat",
        "model_hint": "gemma-4-26b-a4b-it-QAT-4bit",
    }
    monkeypatch.setattr(speed.runner, "candidate_cells", lambda: [cell])
    assert candidate_cell("hunt", "rapid-mlx", "plain") == cell


def test_canary_selection_reports_valid_invalid_and_uninstalled_cells(
    tmp_path, monkeypatch
) -> None:
    cells = [
        {"seat": "coding", "engine": engine, "mode": "plain"}
        for engine in ("rapid-mlx", "mlxcel", "vllm-metal")
    ]
    monkeypatch.setattr(speed.runner, "candidate_cells", lambda: cells)
    entries = (
        {"build": "abc", "valid": True},
        {"build": "abc", "valid": False, "reason": "template mismatch"},
        {"build": "abc", "valid": False, "skipped": True, "reason": "missing binary"},
    )
    for cell, entry in zip(cells, entries, strict=True):
        path = speed.runner.canary_receipt_path(tmp_path, "abc", cell)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry), encoding="utf-8")
    selected = select_canary_cells(tmp_path, "abc", "coding")
    assert [(item[0]["engine"], item[1]) for item in selected] == [
        ("rapid-mlx", True),
        ("mlxcel", False),
        ("vllm-metal", False),
    ]
    assert "template mismatch" in selected[1][2]
    assert "missing binary" in selected[2][2]


def test_all_valid_lists_first_then_runs_only_valid_cells(tmp_path, monkeypatch, capsys) -> None:
    cells = [
        {"seat": "coding", "engine": "rapid-mlx", "mode": "plain"},
        {"seat": "coding", "engine": "mlxcel", "mode": "plain"},
        {"seat": "coding", "engine": "mlx-serve", "mode": "spec"},
    ]
    selected = [
        (cells[0], True, "valid canary"),
        (cells[1], False, "not installed: binary missing"),
        (cells[2], True, "valid canary"),
    ]
    args = speed.argparse.Namespace(seat="coding", prompts=1, repeats=1, pipeline="http://pipeline")
    calls = []
    monkeypatch.setattr(speed.runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(speed.runner, "current_build", lambda: "abc")
    monkeypatch.setattr(speed, "select_canary_cells", lambda *_args: selected)
    monkeypatch.setattr(
        speed,
        "run_seat",
        lambda *_args, engine, mode: (
            calls.append((engine, mode))
            or {"candidate": {"engine": engine, "mode": mode}, "stop_error": None}
        ),
    )
    monkeypatch.setattr(speed, "_save_result", lambda *_args: 0)
    assert speed._run_all_valid(args) == 0
    output = capsys.readouterr().out
    assert "mlxcel:plain:coding | SKIP | not installed: binary missing" in output
    assert output.index("cell | status | reason") < output.index("run | rapid-mlx:plain:coding")
    assert calls == [("rapid-mlx", "plain"), ("mlx-serve", "spec")]


def test_hunt_and_council_json_have_prompts_and_matrix_cells(monkeypatch) -> None:
    assert load_prompts("hunt", 1)[0]["id"] == "hunt-01"
    assert load_prompts("council-json", 1)[0]["id"] == "council-json-01"
    cells = [
        {
            "seat": seat,
            "engine": "vllm-mlx",
            "mode": "plain",
            "workspace": workspace,
            "model": model,
            "model_hint": hint,
        }
        for seat, workspace, model, hint in (
            (
                "hunt",
                "bench-engine-hunt",
                "gemma4_26b_a4b_qat",
                "gemma-4-26b-a4b-it-QAT-4bit",
            ),
            (
                "council-json",
                "bench-engine-council-json",
                "qwen38_27b_h2h",
                "Qwen3.8-27B-4bit",
            ),
        )
    ]
    monkeypatch.setattr(speed.runner, "candidate_cells", lambda: cells)
    assert candidate_cell("hunt", "vllm-mlx", "plain")["workspace"] == "bench-engine-hunt"
    assert candidate_cell("council-json", "vllm-mlx", "plain")["model_hint"] == "Qwen3.8-27B-4bit"


def test_summary_appends_one_pair_row_with_metric_and_streaming(tmp_path) -> None:
    cell = {"engine": "vllm-mlx", "mode": "plain"}
    rows = []
    for repeat, candidate_rate, incumbent_rate in ((0, 20.0, 10.0), (1, 22.0, 11.0)):
        rows.extend(
            (
                {
                    **_row("candidate", repeat, candidate_rate),
                    "ttft_s": 0.4,
                    "streaming": True,
                },
                {
                    **_row("incumbent", repeat, incumbent_rate),
                    "ttft_s": 0.6,
                    "streaming": True,
                },
            )
        )
    summary = summarize(rows)
    path = append_summary_row(tmp_path, "abc", "coding", cell, summary)
    append_summary_row(tmp_path, "abc", "hunt", cell, summary)
    contents = path.read_text(encoding="utf-8")
    assert contents.count("| Seat | Engine | Mode | Metric |") == 1
    assert (
        "| coding | vllm-mlx | plain | decode | 0.400 | 22.000 | 0.600 | 11.000 | 100.0% | yes / yes | FASTER |"
        in contents
    )
    assert "| hunt | vllm-mlx | plain |" in contents

    e2e_rows = []
    for repeat in range(2):
        for arm, rate in (("candidate", 40.0 + repeat), ("incumbent", 20.0 + repeat)):
            e2e_rows.append(
                {
                    **_row(arm, repeat, 0.0),
                    "streaming": False,
                    "decode_tps": None,
                    "throughput_tok_s": None,
                    "e2e_tok_s": rate,
                }
            )
    e2e_summary = summarize(e2e_rows)
    append_summary_row(
        tmp_path, "abc", "daily-moe", {"engine": "mlx-serve", "mode": "spec"}, e2e_summary
    )
    contents = path.read_text(encoding="utf-8")
    assert (
        "| daily-moe | mlx-serve | spec | e2e | 0.400 | 41.000 | 0.400 | 21.000 | 95.2% | no / no | FASTER |"
        in contents
    )


def test_cli_defaults_to_vllm_mlx_and_accepts_all_valid() -> None:
    args = parse_args(["--seat", "coding", "--prompts", "1", "--repeats", "1", "--all-valid"])
    assert args.engine == "vllm-mlx"
    assert args.all_valid is True


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
    assert record["rows"][0]["prompt_id"] == "coding-01"
    assert record["rows"][0]["valid"] is False
    assert str(record["rows"][0]["reason"]).startswith("warm-up failed:")
