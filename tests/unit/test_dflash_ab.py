"""dflash_ab: the settings delta, backup/restore, receipt parsing and the verdict.

The end-to-end cases drive ``run_experiment`` with a fake oMLX/Pipeline (recorded
response shapes) and a fake speed_bench payload, so the OFF/ON switch, the log proof,
the correctness probe and the restore path are exercised without a live stack.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from scripts import dflash_ab as ab

MODEL = "Qwen3.8-27B-4bit"
SEAT = "auto-coding::qwen38coder-dflash"
DRAFT = "/Volumes/data01/omlx-models/Qwen3.8-27B-DFlash2"
ATTACH = (
    "2026-11-20 14:29:41,043 - omlx.engine.batched - INFO - [-] - "
    f"DFlash drafter attached to engine: {MODEL} (kind=dflash2, block=6, layers=[1, 2])"
)
OFF_DECODE = {2000: 40.0, 8000: 35.0, 32000: 25.0}
ON_DECODE = {2000: 56.0, 8000: 49.0, 32000: 35.0}


class Clock:
    """Monotonic clock that advances on every read, so timeouts end quickly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _settings_file(tmp_path: Path, *, enabled: bool = False, draft: str | None = None) -> Path:
    entry: dict = {"dflash_enabled": enabled, "mtp_enabled": False, "max_context_window": 262144}
    if draft:
        entry["dflash_draft_model"] = draft
    path = tmp_path / "model_settings.json"
    path.write_text(
        json.dumps({"models": {MODEL: entry, "other": {"dflash_enabled": False}}}), "utf-8"
    )
    return path


def _draft_dir(tmp_path: Path) -> Path:
    draft = tmp_path / "Qwen3.8-27B-DFlash2"
    draft.mkdir()
    (draft / "config.json").write_text("{}", "utf-8")
    return draft


def _plan(tmp_path: Path, **overrides) -> ab.Plan:
    values = {
        "seat": SEAT,
        "model": MODEL,
        "draft": str(_draft_dir(tmp_path)),
        "sizes": (2000, 8000, 32000),
        "reps": 3,
        "keep_on": False,
        "hunt": {
            "seat": "hunt-reasoning",
            "backend": "omlx-general",
            "engine": "omlx",
            "model": "gemma-4-26b-a4b-it-QAT-4bit",
            "included": False,
            "reason": "the delta toggles only the model under test",
        },
    }
    values.update(overrides)
    return ab.Plan(**values)


class FakeStack:
    """oMLX admin/status/chat plus the Pipeline probe, in their recorded shapes."""

    def __init__(self, settings_file: Path, log_file: Path) -> None:
        self.settings_file = settings_file
        self.log_file = log_file
        self.calls: list[dict] = []
        self.loaded = {MODEL}
        self.proof_on_put = True
        self.auto_unloaded = True
        self.unload_takes = True
        self.stuck_after_enable = False
        self.tool_arguments = json.dumps({"city": "Lisbon", "days": 3, "include_humidity": True})
        self.coding_answer = "126"
        self.reasoning_answer = ab.REASONING_EXPECTED
        self.instruction_answer = ab.INSTRUCTION_EXPECTED

    # -- seams -------------------------------------------------------------------
    def json(self, url, *, method="GET", payload=None, headers=None, timeout=10.0):
        body, _headers = self.json_response(
            url, method=method, payload=payload, headers=headers, timeout=timeout
        )
        return body

    def json_response(self, url, *, method="GET", payload=None, headers=None, timeout=10.0):
        self.calls.append({"url": url, "method": method, "payload": payload})
        route = {"x-portal-route": f"{SEAT};omlx-coding;{MODEL}"}
        if url.endswith("/api/ps"):
            return {"models": [{"name": "qwen3.8:27b", "size": 1024}]}, {}
        if url.endswith("/api/generate"):
            return {}, {}
        if "/admin/reclaim-idle" in url:
            return {"ok": True, "reclaimed_gib": 64}, {}
        if "/v1/models/status" in url:
            return {"models": [{"id": name, "loaded": True} for name in sorted(self.loaded)]}, {}
        if url.endswith("/settings") and method == "PUT":
            return self._put(payload or {}), {}
        if url.endswith("/unload"):
            if self.unload_takes:
                self.loaded.discard(MODEL)
            return {"status": "ok"}, {}
        if url.endswith("/v1/chat/completions"):
            return self._chat(payload or {}), route
        raise AssertionError(f"unexpected call {method} {url}")

    # -- behaviours --------------------------------------------------------------
    def _put(self, payload: dict) -> dict:
        data = json.loads(self.settings_file.read_text("utf-8"))
        data["models"][MODEL].update(payload)
        if payload.get("dflash_enabled") and self.stuck_after_enable:
            self.auto_unloaded = False
            self.unload_takes = False
        self.settings_file.write_text(json.dumps(data), "utf-8")
        if self.auto_unloaded:
            self.loaded.discard(MODEL)
        if payload.get("dflash_enabled") and self.proof_on_put:
            with self.log_file.open("a", encoding="utf-8") as handle:
                handle.write(ATTACH + "\n")
        return {
            "success": True,
            "requires_reload": True,
            "auto_unloaded": self.auto_unloaded,
        }

    def _chat(self, payload: dict) -> dict:
        messages = payload.get("messages") or [{}]
        prompt = str(messages[0].get("content") or "")
        if prompt.startswith("Ready?"):
            self.loaded.add(MODEL)
            return {"model": MODEL, "usage": {"model_load_duration": 7.7}}
        if prompt.startswith("For the city"):
            call = {
                "id": "call_1",
                "type": "function",
                "function": {"name": ab.PROBE_TOOL, "arguments": self.tool_arguments},
            }
            return {
                "model": MODEL,
                "choices": [{"message": {"role": "assistant", "tool_calls": [call]}}],
            }
        if prompt.startswith("What is 17 * 23"):
            answer = self.reasoning_answer
        elif prompt.startswith("Reply with exactly one line"):
            answer = self.instruction_answer
        else:
            answer = self.coding_answer
        return {
            "model": MODEL,
            "choices": [{"message": {"role": "assistant", "content": answer}}],
        }

    def settings_put_payloads(self) -> list[dict]:
        return [
            call["payload"]
            for call in self.calls
            if call["method"] == "PUT" and call["url"].endswith("/settings")
        ]


def _speed_payload(settings_file: Path, sizes: tuple[int, ...], rep: int) -> dict:
    on = ab.dflash_state(ab.read_settings(settings_file), MODEL).get("enabled")
    base = ON_DECODE if on else OFF_DECODE
    rows = [
        {
            "size_tokens": size,
            "prompt_tokens": size,
            "prefill_tps": 1500.0,
            "decode_tps": base[size] + rep * 0.5,
            "load_seconds": 7.7,
            "ttft_s": 1.0 + rep * 0.1,
            "timing_source": "engine",
            "engine_ok": True,
            "completion_tokens": 128,
            "cached_tokens": 0,
        }
        for size in sizes
    ]
    return {"engine": "omlx", "host": "http://omlx", "results": rows, "failures": []}


def _speed_runner(counters: dict[str, int] | None = None):
    """One payload per rep; the rep index restarts for each arm (off_repN / on_repN)."""

    counters = counters if counters is not None else {}

    def run(ctx, model, path):
        arm = path.name.split("_")[0]
        rep = counters.get(arm, 0)
        counters[arm] = rep + 1
        payload = _speed_payload(Path(ctx.settings_file), tuple(ctx.sizes), rep)
        path.write_text(json.dumps(payload), "utf-8")
        return 0

    return run


def _pipeline_runner(ctx, seat, path):
    rows = [
        {
            "size_tokens": size,
            "prompt_tokens": size,
            "decode_tps": 30.0,
            "ttft_s": 1.2,
            "timing_source": "engine",
            "engine_ok": True,
            "backend": "omlx-coding",
            "served_engine": "omlx",
            "served_model": MODEL,
        }
        for size in ctx.sizes
    ]
    path.write_text(json.dumps({"engine": "pipeline", "results": rows, "failures": []}), "utf-8")
    return 0


def _ctx(
    tmp_path: Path,
    *,
    http,
    log: Path,
    settings: Path,
    speed=None,
    pipeline=_pipeline_runner,
    host_quiet=None,
    sizes=(2000, 8000, 32000),
) -> ab.DflashCtx:
    return ab.DflashCtx(
        out_dir=tmp_path / "run",
        pipeline_url="http://pipeline",
        omlx_url="http://omlx",
        ollama_url="http://ollama",
        pipeline_key="pipeline-key",
        omlx_key="omlx-key",
        settings_file=settings,
        server_log=log,
        sizes=sizes,
        reps=3,
        http=http,
        sleep=lambda _seconds: None,
        monotonic=Clock(),
        host_quiet=host_quiet or (lambda: {"returncode": 0, "stdout": "{}", "stderr": ""}),
        speed=speed or _speed_runner(),
        pipeline_bench=pipeline,
    )


def _stack(tmp_path: Path, **kwargs) -> tuple[FakeStack, ab.DflashCtx, Path]:
    settings = _settings_file(tmp_path)
    log = tmp_path / "server.log"
    log.write_text("2026-11-20 14:00:00,000 - omlx.server - INFO - [-] - started\n", "utf-8")
    http = FakeStack(settings, log)
    ctx = _ctx(tmp_path, http=http, log=log, settings=settings, **kwargs)
    return http, ctx, settings


# ----------------------------------------------------------------------------- settings


def test_settings_delta_is_the_plans_two_keys():
    assert ab.settings_delta(DRAFT) == {
        "dflash_enabled": True,
        "dflash_draft_model": DRAFT,
    }


def test_restore_payload_returns_the_prior_state():
    off = ab.dflash_state({"models": {MODEL: {"dflash_enabled": False}}}, MODEL)
    on = ab.dflash_state(
        {"models": {MODEL: {"dflash_enabled": True, "dflash_draft_model": DRAFT}}}, MODEL
    )
    assert ab.restore_payload(off) == {"dflash_enabled": False, "dflash_draft_model": None}
    assert ab.restore_payload(on) == {"dflash_enabled": True, "dflash_draft_model": DRAFT}


def test_dflash_state_reports_a_missing_entry():
    state = ab.dflash_state({"models": {}}, MODEL)
    assert state == {"found": False, "enabled": None, "draft": None}


def test_backup_settings_is_a_timestamped_copy(tmp_path):
    settings = _settings_file(tmp_path)
    backup = ab.backup_settings(settings, "20261120T153000Z")
    assert backup.name == "model_settings.json.dflash-ab-20261120T153000Z"
    assert backup.read_bytes() == settings.read_bytes()


def test_put_settings_surfaces_an_http_error_as_aborted():
    def failing(_url, **_kwargs):
        raise urllib.error.HTTPError(
            "http://omlx", 400, "Bad Request", None, io.BytesIO(b'{"detail": "no draft"}')
        )

    class Rejecting:
        def json(self, url, **kwargs):
            return failing(url, **kwargs)

    ctx = ab.DflashCtx(
        out_dir=Path("/tmp/x"),
        pipeline_url="http://pipeline",
        omlx_url="http://omlx",
        ollama_url="http://ollama",
        pipeline_key="",
        omlx_key="",
        settings_file=Path("/tmp/x/model_settings.json"),
        server_log=Path("/tmp/x/server.log"),
        http=Rejecting(),
    )
    with pytest.raises(ab.AbortedError, match="400"):
        ab.put_settings(ctx, MODEL, ab.settings_delta(DRAFT))


# -------------------------------------------------------------------------------- proof


def test_dflash_proof_matches_only_the_model_it_names():
    text = "\n".join(
        [
            "DFlash drafter attached to engine: Other-Model (kind=dflash2, block=6, layers=[1])",
            ATTACH,
        ]
    )
    assert ab.dflash_proof(text, MODEL) == ATTACH
    assert ab.dflash_proof(text, "Unrelated") is None


def test_dflash_failure_line_is_reported():
    text = f"DFlash drafter load raised for {MODEL} (drafter={DRAFT}): boom -- toggle ignored"
    assert ab.dflash_failure(text, MODEL) is not None
    assert ab.dflash_proof(text, MODEL) is None


def test_wait_for_proof_gives_up_with_a_reason(tmp_path):
    log = tmp_path / "server.log"
    log.write_text("nothing here\n", "utf-8")
    ctx = ab.DflashCtx(
        out_dir=tmp_path,
        pipeline_url="http://pipeline",
        omlx_url="http://omlx",
        ollama_url="http://ollama",
        pipeline_key="",
        omlx_key="",
        settings_file=tmp_path / "model_settings.json",
        server_log=log,
        sleep=lambda _seconds: None,
        monotonic=Clock(),
    )
    result = ab.wait_for_proof(ctx, MODEL, 0)
    assert result["line"] is None
    assert "no DFlash attach line" in result["failure"]


# ------------------------------------------------------------------------------ parsing


def test_summarise_reps_takes_the_median_and_the_spread():
    reps = [
        {"payload": {"results": [{"size_tokens": 2000, "decode_tps": 10.0, "ttft_s": 1.0}]}},
        {"payload": {"results": [{"size_tokens": 2000, "decode_tps": 12.0, "ttft_s": 2.0}]}},
        {"payload": {"results": [{"size_tokens": 2000, "decode_tps": 11.0, "ttft_s": 1.5}]}},
    ]
    summary = ab.summarise_reps(reps, (2000, 8000))
    assert summary["sizes"]["2000"]["decode_median"] == 11.0
    assert summary["sizes"]["2000"]["decode_spread"] == 2.0
    assert summary["sizes"]["2000"]["ttft_median"] == 1.5
    assert summary["sizes"]["8000"]["decode_median"] is None


def test_summarise_reps_keeps_a_missing_rep_out_of_the_median():
    reps = [
        {"payload": {"results": [{"size_tokens": 2000, "decode_tps": 10.0}]}},
        {"payload": {"results": [], "failures": ["FAILED size 2000 tokens: boom"]}},
    ]
    summary = ab.summarise_reps(reps, (2000,))
    assert summary["sizes"]["2000"]["decode_median"] == 10.0
    assert summary["sizes"]["2000"]["decode_spread"] == 0.0
    assert "boom" in summary["failures"][0]


def test_evaluate_tool_records_validity_name_and_types():
    response = {
        "body": {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": ab.PROBE_TOOL,
                                    "arguments": '{"city": "Lisbon", "days": 3, '
                                    '"include_humidity": true}',
                                }
                            }
                        ]
                    }
                }
            ]
        },
        "backend": "omlx-coding",
        "served_model": MODEL,
    }
    probe = ab.evaluate_tool(response)
    assert probe["valid"] is True
    assert probe["selected"] == ab.PROBE_TOOL
    assert probe["argument_types"] == {
        "city": "string",
        "days": "integer",
        "include_humidity": "boolean",
    }


def test_evaluate_tool_flags_invalid_json_and_a_missing_call():
    broken = {
        "body": {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": ab.PROBE_TOOL, "arguments": "{not json"}}
                        ]
                    }
                }
            ]
        }
    }
    assert ab.evaluate_tool(broken)["valid"] is False
    empty = ab.evaluate_tool({"body": {"choices": [{"message": {"content": "hi"}}]}})
    assert empty["selected"] is None
    assert empty["valid"] is False


def test_evaluate_coding_matches_the_expected_value():
    def body(answer: str) -> dict:
        return {"body": {"choices": [{"message": {"content": answer}}]}}

    assert ab.evaluate_coding(body("126"))["matched"] is True
    assert ab.evaluate_coding(body("The output is 126."))["matched"] is True
    assert ab.evaluate_coding(body("1126"))["matched"] is False
    assert ab.evaluate_coding(body(""))["matched"] is False


# ------------------------------------------------------------------------------- verdict


def _arm(decode: dict[int, float], spread: float = 0.0, *, engine_ok: bool = True) -> dict:
    sizes = {
        str(size): {
            "decode_median": value,
            "decode_spread": spread,
            "ttft_median": 1.0,
            "timing_sources": ["engine"],
        }
        for size, value in decode.items()
    }
    return {
        "label": "off",
        "speed": {"sizes": sizes},
        "pipeline": {
            "rows": [
                {
                    "size_tokens": 2000,
                    "backend": "omlx-coding",
                    "served_model": MODEL,
                    "engine_ok": engine_ok,
                }
            ],
            "failures": [],
        },
        "probe": {
            "coding": {
                "matched": True,
                "answer": "126",
                "backend": "omlx-coding",
                "served_model": MODEL,
            },
            "tool": {
                "selected": ab.PROBE_TOOL,
                "valid": True,
                "argument_types": {"city": "string"},
                "backend": "omlx-coding",
                "served_model": MODEL,
            },
            "reasoning": {
                "matched": True,
                "answer": ab.REASONING_EXPECTED,
                "backend": "omlx-coding",
                "served_model": MODEL,
            },
            "instruction": {
                "matched": True,
                "answer": ab.INSTRUCTION_EXPECTED,
                "backend": "omlx-coding",
                "served_model": MODEL,
            },
        },
    }


def test_pass_needs_a_gain_beyond_the_spread_at_every_size():
    comparison = ab.compare_arms(_arm(OFF_DECODE), _arm(ON_DECODE), (2000, 8000, 32000))
    assert comparison["status"] == "PASS"
    assert all(row["beyond"] for row in comparison["rows"])


def test_a_gain_inside_the_spread_is_not_a_pass():
    comparison = ab.compare_arms(
        _arm(OFF_DECODE, spread=40.0), _arm(ON_DECODE), (2000, 8000, 32000)
    )
    assert comparison["status"] == "WITHIN_SPREAD"


def test_one_slower_size_is_not_a_clean_pass():
    slower = dict(ON_DECODE)
    slower[32000] = 20.0
    comparison = ab.compare_arms(_arm(OFF_DECODE), _arm(slower), (2000, 8000, 32000))
    assert comparison["status"] == "NO_GAIN"


def test_a_wrong_engine_row_makes_the_run_invalid():
    comparison = ab.compare_arms(
        _arm(OFF_DECODE), _arm(ON_DECODE, engine_ok=False), (2000, 8000, 32000)
    )
    assert comparison["status"] == "INVALID"
    assert "wrong engine" in comparison["invalid"][0]


def test_a_probe_served_by_another_backend_is_invalid():
    off = _arm(OFF_DECODE)
    on = _arm(ON_DECODE)
    on["probe"]["tool"]["backend"] = "ollama-general"
    on["probe"]["tool"]["served_model"] = "qwen3.8:27b-ctx32k"
    comparison = ab.compare_arms(off, on, (2000, 8000, 32000), backend="omlx-coding", model=MODEL)
    assert comparison["status"] == "INVALID"
    assert "tool probe served ollama-general" in comparison["invalid"][0]


def test_a_changed_tool_name_is_a_correctness_regression():
    off = _arm(OFF_DECODE)
    on = _arm(ON_DECODE)
    on["probe"]["tool"]["selected"] = "list_saved_reports"
    comparison = ab.compare_arms(off, on, (2000, 8000, 32000))
    assert comparison["status"] == "CORRECTNESS_REGRESSION"
    assert any("tool selection changed" in item for item in comparison["problems"])


# ------------------------------------------------------------------------------- receipt


def test_receipt_lists_a_failed_speed_size():
    run = {
        "stamp": "x",
        "sizes": [2000],
        "off": {"speed": {"sizes": {}, "failures": ["FAILED size 2000 tokens: timeout"]}},
        "on": {},
    }
    assert "off speed failure: FAILED size 2000 tokens: timeout" in ab.render_receipt(run)


def test_an_aborted_run_still_renders_a_receipt():
    receipt = ab.render_receipt(
        {"stamp": "20261120T153000Z", "abort": "host not quiet", "sizes": [2000]}
    )
    assert "aborted: host not quiet" in receipt
    assert "NOT MEASURED" in receipt


# --------------------------------------------------------------------------- end to end


def test_run_experiment_measures_both_arms_and_restores_off(tmp_path):
    http, ctx, settings = _stack(tmp_path)
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert run["abort"] is None
    assert run["comparison"]["status"] == "PASS"
    assert run["off"]["speed"]["sizes"]["2000"]["decode_median"] == 40.5
    assert run["on"]["speed"]["sizes"]["2000"]["decode_median"] == 56.5
    assert run["on"]["proof"]["line"] == ATTACH
    assert http.settings_put_payloads() == [
        ab.settings_delta(str(ctx.out_dir.parent / "Qwen3.8-27B-DFlash2"))
        | {"dflash_enabled": True},
        {"dflash_enabled": False, "dflash_draft_model": None},
    ]
    assert run["restore"]["ok"] is True
    assert ab.dflash_state(ab.read_settings(settings), MODEL)["enabled"] is False

    receipt = ab.write_receipt(run, ctx.out_dir).read_text("utf-8")
    assert ATTACH in receipt
    assert "**PASS**" in receipt
    assert "hunt seat `hunt-reasoning`" in receipt
    assert "| 2000 | 40.5 |" in receipt


def test_a_missing_attach_line_aborts_the_on_arm_and_still_restores(tmp_path):
    http, ctx, settings = _stack(tmp_path)
    http.proof_on_put = False
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert "DFlash is not proven on" in run["abort"]
    assert http.settings_put_payloads()[-1] == {
        "dflash_enabled": False,
        "dflash_draft_model": None,
    }
    assert run["restore"]["ok"] is True
    assert ab.dflash_state(ab.read_settings(settings), MODEL)["enabled"] is False


def test_an_engine_that_never_unloads_aborts_and_still_restores(tmp_path):
    http, ctx, settings = _stack(tmp_path)
    http.stuck_after_enable = True
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert "did not unload" in run["abort"]
    assert http.settings_put_payloads()[-1] == {
        "dflash_enabled": False,
        "dflash_draft_model": None,
    }
    assert run["restore"]["ok"] is True
    assert ab.dflash_state(ab.read_settings(settings), MODEL)["enabled"] is False


def test_ctrl_c_during_the_on_arm_still_restores(tmp_path):
    http, ctx, _settings = _stack(tmp_path)
    calls = {"count": 0}

    def interrupted(ctx_, model, path):
        calls["count"] += 1
        if calls["count"] > ctx_.reps:
            raise KeyboardInterrupt
        return _speed_runner()(ctx_, model, path)

    ctx.speed = interrupted
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert "interrupted" in run["abort"]
    assert http.settings_put_payloads()[-1] == {
        "dflash_enabled": False,
        "dflash_draft_model": None,
    }
    assert run["restore"]["ok"] is True


def test_a_noisy_host_aborts_before_any_settings_write(tmp_path):
    http, ctx, _settings = _stack(
        tmp_path, host_quiet=lambda: {"returncode": 1, "stdout": "", "stderr": "busy"}
    )
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert "precondition failed" in run["abort"]
    assert http.settings_put_payloads() == []
    assert "restore" not in run


def test_dflash_already_on_aborts_before_measuring(tmp_path):
    settings = _settings_file(tmp_path, enabled=True, draft=DRAFT)
    log = tmp_path / "server.log"
    log.write_text("", "utf-8")
    http = FakeStack(settings, log)
    ctx = _ctx(tmp_path, http=http, log=log, settings=settings)
    run = ab.run_experiment(ctx, _plan(tmp_path))

    assert "already enabled" in run["abort"]
    assert http.settings_put_payloads() == []


def test_keep_on_leaves_dflash_on_only_after_a_pass(tmp_path):
    http, ctx, settings = _stack(tmp_path)
    run = ab.run_experiment(ctx, _plan(tmp_path, keep_on=True))

    assert run["kept_on"] is True
    assert "restore" not in run
    assert ab.dflash_state(ab.read_settings(settings), MODEL)["enabled"] is True
    assert len(http.settings_put_payloads()) == 1


def test_keep_on_still_restores_when_the_pass_bar_is_missed(tmp_path):
    _http, ctx, settings = _stack(tmp_path)
    plan = _plan(tmp_path, keep_on=True)
    # An OFF arm faster than the ON arm cannot pass; the delta itself is unchanged.
    baseline = dict(OFF_DECODE)

    def slow_on(ctx_, model, path):
        on = ab.dflash_state(ab.read_settings(Path(ctx_.settings_file)), MODEL).get("enabled")
        values = {size: (value - 20.0 if on else value) for size, value in baseline.items()}
        rows = [
            {"size_tokens": size, "decode_tps": value, "ttft_s": 1.0, "engine_ok": True}
            for size, value in values.items()
        ]
        path.write_text(json.dumps({"results": rows, "failures": []}), "utf-8")
        return 0

    ctx.speed = slow_on
    run = ab.run_experiment(ctx, plan)

    assert run["comparison"]["status"] == "NO_GAIN"
    assert run["kept_on"] is False
    assert run["restore"]["ok"] is True
    assert ab.dflash_state(ab.read_settings(settings), MODEL)["enabled"] is False


def test_run_experiment_creates_out_dir_before_the_arms_write(tmp_path):
    http, ctx, _settings = _stack(tmp_path)
    assert not ctx.out_dir.exists()
    seen: list[bool] = []
    base = _speed_runner()

    def run(ctx_, model, path):
        seen.append(path.parent.is_dir())
        return base(ctx_, model, path)

    ctx.speed = run
    run_ = ab.run_experiment(ctx, _plan(tmp_path))

    assert run_["abort"] is None
    assert run_["comparison"]["status"] == "PASS"
    assert seen == [True] * (2 * ctx.reps)
    assert (ctx.out_dir / "off_rep1.json").is_file()
    assert (ctx.out_dir / "off_pipeline.json").is_file()
    assert (ctx.out_dir / "on_pipeline.json").is_file()
