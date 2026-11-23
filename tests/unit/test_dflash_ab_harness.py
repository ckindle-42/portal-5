"""Regression net for the DFlash A/B harness audit (run 20261123T023745Z).

Root causes fixed here: the Pipeline's capped-workspace seal swallowed
client-only tool calls (both probe arms read selected=None), and sampled
early-EOS completions (2→128 tokens) made decode tok/s incomparable across
reps. These tests pin the INVALID_BASELINE grading, ON-only regressions, the
deterministic sampling/cache-control plumbing, and the per-rep stats capture.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

import portal.platform.inference.router.non_streaming as ns
from scripts import dflash_ab as ab
from scripts import speed_bench

MODEL = "Qwen3.8-27B-4bit"
SEAT = "auto-coding::qwen38coder-dflash"
OFF_DECODE = {2000: 14.8, 8000: 14.8, 32000: 12.3}
ON_DECODE = {2000: 27.8, 8000: 36.4, 32000: 17.1}


def _probe(
    *, coding: bool = True, tool: bool = True, reasoning: bool = True, instruction: bool = True
) -> dict[str, Any]:
    served = {"backend": "omlx-coding", "served_model": MODEL}
    return {
        "coding": {"matched": coding, "answer": "126" if coding else "10", **served},
        "tool": {
            "selected": ab.PROBE_TOOL if tool else None,
            "valid": tool,
            "argument_types": {"city": "string"} if tool else {},
            **served,
        },
        "reasoning": {
            "matched": reasoning,
            "answer": ab.REASONING_EXPECTED if reasoning else "400",
            **served,
        },
        "instruction": {
            "matched": instruction,
            "answer": ab.INSTRUCTION_EXPECTED if instruction else "READY 10",
            **served,
        },
    }


def _arm(label: str, decode: dict[int, float], probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "speed": {
            "sizes": {
                str(size): {"decode_median": value, "decode_spread": 0.0}
                for size, value in decode.items()
            }
        },
        "pipeline": {"rows": [], "failures": []},
        "probe": probe,
    }


# --------------------------------------------------------------------------- grading


def test_both_arms_failing_the_tool_probe_is_invalid_baseline():
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, _probe(tool=False)),
        _arm("on", ON_DECODE, _probe(tool=False)),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "INVALID_BASELINE"
    assert comparison["status"] != "CORRECTNESS_REGRESSION"
    assert any("OFF tool probe" in reason for reason in comparison["baseline_invalid"])


@pytest.mark.parametrize("failing", ["coding", "reasoning", "instruction"])
def test_any_off_answer_probe_failure_is_invalid_baseline(failing: str):
    off_probe = _probe(**{failing: False})
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, off_probe),
        _arm("on", ON_DECODE, _probe()),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "INVALID_BASELINE"
    assert any(f"OFF {failing}" in reason for reason in comparison["baseline_invalid"])


def test_on_only_tool_failure_is_still_a_correctness_regression():
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, _probe()),
        _arm("on", ON_DECODE, _probe(tool=False)),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "CORRECTNESS_REGRESSION"
    assert comparison["baseline_invalid"] == []


@pytest.mark.parametrize("failing", ["coding", "reasoning", "instruction"])
def test_on_only_answer_failure_is_still_a_correctness_regression(failing: str):
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, _probe()),
        _arm("on", ON_DECODE, _probe(**{failing: False})),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "CORRECTNESS_REGRESSION"
    assert comparison["baseline_invalid"] == []
    assert any(failing in problem for problem in comparison["problems"])


def test_all_four_probes_passing_with_a_gain_is_a_pass():
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, _probe()),
        _arm("on", ON_DECODE, _probe()),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "PASS"


def test_a_wrong_engine_row_outranks_a_broken_baseline():
    off = _arm("off", OFF_DECODE, _probe(tool=False))
    on = _arm("on", ON_DECODE, _probe())
    on["pipeline"]["rows"] = [{"size_tokens": 2000, "engine_ok": False}]
    comparison = ab.compare_arms(off, on, (2000, 8000, 32000))
    assert comparison["status"] == "INVALID"


def test_probes_absent_from_an_old_run_shape_are_not_baseline_failures():
    legacy = {name: _probe()[name] for name in ("coding", "tool")}
    comparison = ab.compare_arms(
        _arm("off", OFF_DECODE, legacy),
        _arm("on", ON_DECODE, legacy),
        (2000, 8000, 32000),
    )
    assert comparison["status"] == "PASS"
    assert comparison["baseline_invalid"] == []


def test_varying_completion_lengths_are_flagged_as_not_like_for_like():
    off = _arm("off", OFF_DECODE, _probe())
    off["speed"]["sizes"]["8000"]["completion_tokens"] = [128, 2, 128]
    comparison = ab.compare_arms(off, _arm("on", ON_DECODE, _probe()), (2000, 8000, 32000))
    assert any("completion lengths vary" in note for note in comparison["notes"])


# --------------------------------------------------------------- sampling plumbing


def _capture_run_bench(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake(engine, host, target, sizes, **kwargs):
        captured.update(kwargs, engine=engine, host=host, target=target, sizes=sizes)
        return 0

    monkeypatch.setattr(speed_bench, "run_bench", fake)
    return captured


def test_default_speed_passes_deterministic_controls(monkeypatch, tmp_path):
    captured = _capture_run_bench(monkeypatch)
    ctx = SimpleNamespace(
        out_dir=tmp_path / "20261123T023745Z",
        omlx_url="http://omlx",
        omlx_key="k",
        sizes=(2000, 8000),
    )
    assert ab._default_speed(ctx, MODEL, ctx.out_dir / "off_rep1.json") == 0
    assert captured["engine"] == "omlx"
    assert captured["temperature"] == ab.AB_TEMPERATURE == 0.0
    assert captured["seed"] == ab.AB_SEED
    assert captured["ignore_eos"] is True
    assert captured["cache_bust"] == "20261123T023745Z-off_rep1"


def test_default_pipeline_passes_deterministic_controls(monkeypatch, tmp_path):
    captured = _capture_run_bench(monkeypatch)
    ctx = SimpleNamespace(
        out_dir=tmp_path / "20261123T023745Z",
        pipeline_url="http://pipeline",
        pipeline_key="k",
        sizes=(2000,),
    )
    assert ab._default_pipeline(ctx, SEAT, ctx.out_dir / "on_pipeline.json") == 0
    assert captured["engine"] == "pipeline"
    assert captured["temperature"] == 0.0
    assert captured["seed"] == ab.AB_SEED
    assert captured["ignore_eos"] is True
    assert captured["cache_bust"] == "20261123T023745Z-on_pipeline"


def _measure_row() -> dict[str, Any]:
    return {
        "prompt_tokens": 1467,
        "prefill_tps": 1500.0,
        "decode_tps": 30.0,
        "load_seconds": None,
        "ttft_s": 0.5,
        "total_s": 4.5,
        "timing_source": "engine",
    }


def test_cache_bust_nonces_are_unique_per_rep_and_size(monkeypatch):
    seen: list[dict[str, Any]] = []

    def fake_measure(engine, host, target, prompt, api_key, timeout, **kwargs):
        seen.append(kwargs)
        return _measure_row()

    monkeypatch.setattr(speed_bench, "_measure", fake_measure)
    for rep in (1, 2):
        speed_bench.run_bench(
            "omlx",
            "http://omlx",
            MODEL,
            [2000, 8000],
            temperature=0.0,
            seed=42,
            ignore_eos=True,
            cache_bust=f"run-off_rep{rep}",
        )
    nonces = [kwargs["nonce"] for kwargs in seen]
    assert nonces == [
        "run-off_rep1-2000",
        "run-off_rep1-8000",
        "run-off_rep2-2000",
        "run-off_rep2-8000",
    ]
    assert len(set(nonces)) == 4
    assert all(k["temperature"] == 0.0 and k["seed"] == 42 and k["ignore_eos"] for k in seen)


class _JsonResp(io.BytesIO):
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_request_omlx_payload_carries_the_controls(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return _JsonResp(json.dumps({"usage": {}}).encode("utf-8"))

    monkeypatch.setattr(speed_bench, "_post", fake_post)
    speed_bench.request_omlx(
        "http://omlx", MODEL, "fill", temperature=0.0, seed=42, ignore_eos=True, nonce="n1"
    )
    payload = captured["payload"]
    assert payload["temperature"] == 0.0
    assert payload["seed"] == 42
    assert payload["ignore_eos"] is True
    assert payload["messages"][0]["content"] == "[bench-nonce n1]\nfill"


def test_request_omlx_defaults_leave_engine_sampling_untouched(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return _JsonResp(json.dumps({"usage": {}}).encode("utf-8"))

    monkeypatch.setattr(speed_bench, "_post", fake_post)
    speed_bench.request_omlx("http://omlx", MODEL, "fill")
    payload = captured["payload"]
    assert "temperature" not in payload
    assert "seed" not in payload
    assert "ignore_eos" not in payload
    assert payload["messages"][0]["content"] == "fill"


def test_request_pipeline_payload_carries_the_controls(monkeypatch):
    captured: dict[str, Any] = {}
    lines = [
        b'data: {"portal_timings": {"answer_tps": 30.0}}\n\n',
        b'data: {"usage": {"prompt_tokens": 1467, "completion_tokens": 128}}\n\n',
        b"data: [DONE]\n\n",
    ]

    def fake_post(url, payload, timeout, headers=None):
        captured["payload"] = payload
        return _JsonResp(b"".join(lines))

    monkeypatch.setattr(speed_bench, "_post", fake_post)
    speed_bench.request_pipeline(
        "http://pipeline", SEAT, "fill", temperature=0.0, seed=42, ignore_eos=True, nonce="n2"
    )
    payload = captured["payload"]
    assert payload["temperature"] == 0.0
    assert payload["seed"] == 42
    assert payload["ignore_eos"] is True
    assert payload["messages"][0]["content"] == "[bench-nonce n2]\nfill"


def test_omlx_metrics_records_completion_and_cached_tokens():
    body = {
        "usage": {
            "prompt_tokens": 1467,
            "completion_tokens": 128,
            "prompt_eval_duration": 1.0,
            "generation_duration": 5.0,
            "prompt_tokens_details": {"cached_tokens": 0},
        }
    }
    row = speed_bench.omlx_metrics(body)
    assert row["completion_tokens"] == 128
    assert row["cached_tokens"] == 0
    bare = speed_bench.omlx_metrics({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    assert bare["completion_tokens"] == 5
    assert bare["cached_tokens"] is None


def test_run_bench_report_records_the_applied_controls(tmp_path, monkeypatch):
    monkeypatch.setattr(speed_bench, "_measure", lambda *_a, **_kw: _measure_row())
    out = tmp_path / "rep.json"
    speed_bench.run_bench(
        "omlx",
        "http://omlx",
        MODEL,
        [2000],
        out=str(out),
        temperature=0.0,
        seed=42,
        ignore_eos=True,
        cache_bust="run-off_rep1",
    )
    report = json.loads(out.read_text("utf-8"))
    assert report["controls"] == {
        "temperature": 0.0,
        "seed": 42,
        "ignore_eos": True,
        "cache_bust": "run-off_rep1",
    }
    plain = tmp_path / "plain.json"
    speed_bench.run_bench("omlx", "http://omlx", MODEL, [2000], out=str(plain))
    assert "controls" not in json.loads(plain.read_text("utf-8"))


# ------------------------------------------------------------------------- probes


class _ProbeHttp:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def json_response(self, url, *, method="GET", payload=None, headers=None, timeout=10.0):
        self.payloads.append(payload)
        prompt = str((payload["messages"][0] or {}).get("content") or "")
        if prompt.startswith("For the city"):
            call = {"function": {"name": ab.PROBE_TOOL, "arguments": '{"city": "Lisbon"}'}}
            message: dict[str, Any] = {"tool_calls": [call]}
        elif prompt.startswith("What is 17 * 23"):
            message = {"content": ab.REASONING_EXPECTED}
        elif prompt.startswith("Reply with exactly one line"):
            message = {"content": ab.INSTRUCTION_EXPECTED}
        else:
            message = {"content": ab.CODING_EXPECTED}
        body = {"choices": [{"message": message}]}
        return body, {"x-portal-route": f"{SEAT};omlx-coding;{MODEL}"}


def test_probe_seat_sends_greedy_sampling_on_all_four_prompts():
    http = _ProbeHttp()
    ctx = SimpleNamespace(pipeline_url="http://pipeline", pipeline_key="k", http=http)
    probe = ab.probe_seat(ctx, SEAT)
    assert set(probe) == {"coding", "tool", "reasoning", "instruction"}
    assert len(http.payloads) == 4
    assert all(p["temperature"] == 0.0 and p["seed"] == ab.AB_SEED for p in http.payloads)
    tool_payload = http.payloads[1]
    assert tool_payload["portal_client_tools_only"] is True
    assert [t["function"]["name"] for t in tool_payload["tools"]] == [
        ab.PROBE_TOOL,
        "list_saved_reports",
    ]
    assert probe["coding"]["matched"] is True
    assert probe["tool"]["valid"] is True
    assert probe["reasoning"]["matched"] is True
    assert probe["instruction"]["matched"] is True


def test_evaluate_instruction_normalizes_whitespace_only():
    def body(answer: str) -> dict:
        return {"body": {"choices": [{"message": {"content": answer}}]}}

    assert ab.evaluate_instruction(body("  READY  11 \n"))["matched"] is True
    assert ab.evaluate_instruction(body("READY 12"))["matched"] is False
    assert ab.evaluate_instruction(body("ready 11"))["matched"] is False


def test_evaluate_reasoning_matches_the_final_number():
    def body(answer: str) -> dict:
        return {"body": {"choices": [{"message": {"content": answer}}]}}

    assert ab.evaluate_reasoning(body("17*23=391\n391+19=410"))["matched"] is True
    assert ab.evaluate_reasoning(body("4100"))["matched"] is False


# ------------------------------------------------------------- stats and receipt

MTP_LINE = (
    "2026-11-22 20:49:30,000 - omlx.patches.mlx_lm_mtp.batch_generator - INFO - [-] - "
    "MTP[8] finish=length tokens=128 cycles=22 tok/cycle=5.82 accept=104/105 (99.0%) "
    "depth[d1=22/22] emits[init=2,draft=104,bonus=22,verify=0] "
    "timing[backbone=100.0ms mtp=10.0ms sample=1.0ms cache=2.0ms]"
)


def test_speculative_stats_parses_the_engine_log_format():
    stats = ab.speculative_stats(MTP_LINE + "\nunrelated line\n")
    assert stats == [
        {
            "uid": 8,
            "finish": "length",
            "tokens": 128,
            "cycles": 22,
            "tok_per_cycle": "5.82",
            "accepted": 104,
            "drafted": 105,
            "rate": "99.0%",
        }
    ]


def test_speculative_stats_handles_a_zero_cycle_sequence():
    line = "MTP[2] finish=stop tokens=2 cycles=0 tok/cycle=0.00 accept=0/0 (n/a) emits[x]"
    stats = ab.speculative_stats(line)
    assert stats[0]["rate"] == "n/a"
    assert stats[0]["cycles"] == 0
    assert ab.speculative_stats("no counters here") == []


def test_receipt_renders_the_baseline_verdict_and_per_rep_tables():
    run = {
        "stamp": "x",
        "sizes": [2000],
        "reps": 1,
        "off": {
            "reps": [
                {
                    "file": "off_rep1.json",
                    "payload": {
                        "results": [
                            {
                                "size_tokens": 2000,
                                "decode_tps": 14.8,
                                "completion_tokens": 128,
                                "cached_tokens": 0,
                            }
                        ]
                    },
                }
            ],
            "speculative_stats": [],
        },
        "on": {
            "reps": [
                {
                    "file": "on_rep1.json",
                    "payload": {
                        "results": [
                            {
                                "size_tokens": 2000,
                                "decode_tps": 27.8,
                                "completion_tokens": 128,
                                "cached_tokens": 0,
                            }
                        ]
                    },
                }
            ],
            "speculative_stats": ab.speculative_stats(MTP_LINE),
        },
        "comparison": {
            "status": "INVALID_BASELINE",
            "rows": [],
            "problems": [],
            "invalid": [],
            "baseline_invalid": ["OFF tool probe returned no valid fetch_weather call"],
            "notes": [],
        },
    }
    receipt = ab.render_receipt(run)
    assert "**INVALID_BASELINE**" in receipt
    assert "invalid baseline: OFF tool probe" in receipt
    assert "Per-rep decode samples" in receipt
    assert "| on | 1 | 2000 | 128 | 27.8 | 0 |" in receipt
    assert "draft/verify counters" in receipt
    assert "| on | 8 | length | 128 | 22 | 104/105 | 99.0% |" in receipt


def test_run_arm_captures_the_arms_speculative_counters(tmp_path):
    from tests.unit.test_dflash_ab import _plan, _stack

    http, ctx, _settings = _stack(tmp_path)
    base_runner = ctx.speed

    def logging_runner(ctx_, model, path):
        with ctx_.server_log.open("a", encoding="utf-8") as handle:
            handle.write(MTP_LINE + "\n")
        return base_runner(ctx_, model, path)

    ctx.speed = logging_runner
    record = ab.run_arm(ctx, _plan(tmp_path), label="on", unload=False, prove=False)
    assert record["speculative_stats"][0]["tokens"] == 128
    assert record["speculative_stats"][0]["rate"] == "99.0%"


# ------------------------------------------------- Pipeline client-tools-only seal


@pytest.fixture
def seal_ws(monkeypatch: pytest.MonkeyPatch):
    ws = "test-dflash-seal-ws"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m", "max_tool_calls": 10})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "apply_eval_scope", lambda _b, tools: tools)
    return ws


def _seal_backend() -> Any:
    return SimpleNamespace(
        id="b",
        type="omlx",
        chat_url="http://engine/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h if h in ["m"] else None,
    )


class _SealClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = list(responses)
        self.bodies: list[dict] = []

    async def post(self, url: str, json: dict, timeout: Any) -> httpx.Response:  # noqa: A002
        self.bodies.append(dict(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _tool_reply(name: str) -> httpx.Response:
    call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": "{}"}}
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}}]},
    )


async def test_client_tools_only_calls_return_on_a_capped_workspace(monkeypatch, seal_ws):
    client = _SealClient([_tool_reply("fetch_weather")])
    monkeypatch.setattr(ns, "_http_client", client)
    body = {
        "messages": [{"role": "user", "content": "call fetch_weather for Lisbon"}],
        "portal_client_tools_only": True,
        "tools": [{"type": "function", "function": {"name": "fetch_weather", "parameters": {}}}],
        "tool_choice": "auto",
    }
    result = await ns._try_non_streaming(_seal_backend(), body, seal_ws, 0.0)
    assert result is not None
    message = json.loads(result.body)["choices"][0]["message"]
    assert message["tool_calls"][0]["function"]["name"] == "fetch_weather"
    assert len(client.bodies) == 1  # no cited-synthesis second turn


async def test_capped_workspace_still_seals_without_the_client_flag(monkeypatch, seal_ws):
    client = _SealClient(
        [
            _tool_reply("fetch_weather"),
            httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "synthesized"}}]},
            ),
        ]
    )
    monkeypatch.setattr(ns, "_http_client", client)
    body = {"messages": [{"role": "user", "content": "call fetch_weather for Lisbon"}]}
    result = await ns._try_non_streaming(_seal_backend(), body, seal_ws, 0.0)
    assert result is not None
    message = json.loads(result.body)["choices"][0]["message"]
    assert not message.get("tool_calls")
    assert message["content"] == "synthesized"
    assert len(client.bodies) == 2
    assert client.bodies[1]["tools"] is None
