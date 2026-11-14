"""Offline contracts for the candidate engine-evaluation runner."""

from __future__ import annotations

import contextlib
import io
import json
import urllib.error
from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from tests.benchmarks import engine_eval_instrument as instrument
from tests.benchmarks import engine_eval_runner as runner


def test_candidate_cells_use_registry_argv_and_fixed_pipeline_backend() -> None:
    cells = runner.candidate_cells()

    assert cells
    assert {cell["seat"] for cell in cells} == {
        "daily-moe",
        "coding",
        "task-router",
        "hunt",
        "council-json",
    }
    assert all(cell["engine_kind"] == "managed" for cell in cells)
    assert all(cell["backend"] for cell in cells)
    assert all(cell["argv"] or cell["launch_error"] for cell in cells)
    assert all(cell["backend"] != "eval-openai" or cell["port"] == 11234 for cell in cells)


def test_production_models_are_unloaded_before_candidate_start(monkeypatch, capsys) -> None:
    state = {"ollama": {"production:tag": True}, "omlx": {"production/model": True}}
    calls = []

    def fake_http_json(url, payload=None, timeout=30):
        calls.append((url, payload))
        if url.endswith("/api/ps"):
            return {"models": [{"name": name} for name in state["ollama"]]}
        if url.endswith("/v1/models/status"):
            return {
                "models": [
                    {"id": name, "loaded": loaded, "actual_size": 10}
                    for name, loaded in state["omlx"].items()
                ]
            }
        if url.endswith("/api/generate"):
            assert payload == {"model": "production:tag", "keep_alive": 0, "stream": False}
            state["ollama"].clear()
            return {"done": True}
        if url.endswith("/production%2Fmodel/unload"):
            state["omlx"]["production/model"] = False
            return {"unloaded": True}
        raise AssertionError(url)

    monkeypatch.setattr(runner.h2h, "http_json", fake_http_json)
    cfg = {
        "engines": {
            "ollama": {"base": "http://127.0.0.1:11434"},
            "omlx": {"base": "http://127.0.0.1:8085"},
        }
    }

    result = runner._prepare_production_models(cfg)

    assert result["valid"] is True
    assert result["unloaded"] == {"ollama": ["production:tag"], "omlx": ["production/model"]}
    assert any(
        payload == {"model": "production:tag", "keep_alive": 0, "stream": False}
        for _, payload in calls
    )
    assert any(
        "unloaded | ollama | production:tag" in line
        for line in capsys.readouterr().out.splitlines()
    )


def test_failed_production_unload_is_recorded_and_stops_before_swap_gate(monkeypatch) -> None:
    receipt = {}
    gate_calls = []
    host_prep = {"valid": False, "failures": ["oMLX unload failed for loaded/model"]}
    monkeypatch.setattr(runner, "_prepare_production_models", lambda _cfg: host_prep)
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: gate_calls.append("gate"))
    cell = {"launch_error": None, "port": 11234}

    with pytest.raises(runner.Stage3BlockedError, match="pre-canary unload failed"):
        runner._execute_candidate_cell(
            cell,
            "http://pipeline",
            {},
            receipt,
            (Path("stdout"), Path("stderr")),
            lambda: None,
        )

    assert receipt["host_prep"] == host_prep
    assert gate_calls == []


def test_candidate_parity_labels_prompt_rendering_difference() -> None:
    request = {"messages": [{"role": "user", "content": "OK"}], "temperature": 0, "max_tokens": 64}
    left = {
        "request": {**request, "portal_backend": "eval-a"},
        "outputs": [{"content": "OK"}, {"content": "OK"}],
        "rendered_prompt_token_count": 3506,
        "effective_temperature": 0,
    }
    right = {
        "request": {**request, "portal_backend": "eval-b"},
        "outputs": [{"content": "OK"}, {"content": "OK"}],
        "rendered_prompt_token_count": 3100,
        "effective_temperature": None,
        "effective_temperature_note": "engine log has no effective sampling readback",
    }

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is False
    assert result["classification"] == "chat_template_rendering_mismatch"
    assert result["rendered_prompt_token_counts"] == {"left": 3506, "right": 3100}
    assert result["rendered_prompt_token_delta"]["within_tolerance"] is False
    assert "effective sampling readback" in result["findings"][0]


def test_candidate_parity_accepts_a_count_inside_the_stated_tolerance() -> None:
    request = {"messages": [{"role": "user", "content": "OK"}], "temperature": 0, "max_tokens": 64}
    left = {
        "request": {**request, "portal_backend": "eval-a"},
        "outputs": [{"content": "OK"}],
        "rendered_prompt_token_count": 3506,
        "effective_temperature": 0,
    }
    right = {
        "request": {**request, "portal_backend": "eval-b"},
        "outputs": [{"content": "OK"}],
        "rendered_prompt_token_count": 3474,
        "effective_temperature": 0,
    }

    result = runner._compare_candidate_parity(left, right)

    assert result["classification"] == "match"
    assert result["rendered_prompt_token_delta"]["delta"] == 32
    assert result["prompt_token_tolerance"] == runner.parity_settings()["prompt_token_tolerance"]


def test_the_protocol_carries_the_operator_parity_rule() -> None:
    """K and the prompt tolerance are protocol numbers set by the operator, not code."""
    settings = yaml.safe_load(runner.PROTOCOL.read_text(encoding="utf-8"))["template_parity"]

    assert settings["set_by"] == "operator"
    assert settings["set_on"] == "2026-11-14"
    assert settings["prompt_token_tolerance"] == 0.02
    assert isinstance(settings["prefix_tokens"], int)
    assert settings["prefix_tokens"] >= 0
    assert runner.parity_settings() == {
        "prompt_token_tolerance": float(settings["prompt_token_tolerance"]),
        "prefix_tokens": settings["prefix_tokens"],
    }


def test_a_protocol_without_the_parity_rule_blocks_rather_than_guesses(
    monkeypatch, tmp_path
) -> None:
    bare = tmp_path / "protocol.yaml"
    bare.write_text("status: APPROVED\n", encoding="utf-8")
    monkeypatch.setattr(runner, "PROTOCOL", bare)

    with pytest.raises(runner.Stage3BlockedError, match="template_parity"):
        runner.parity_settings()


def _drift_pair(left_content: str, right_content: str) -> tuple[dict, dict]:
    request = {"messages": [{"role": "user", "content": "OK"}], "temperature": 0, "max_tokens": 64}
    left = {
        "engine": "mlx-serve",
        "request": {**request, "portal_backend": "eval-a"},
        "outputs": [{"content": left_content}],
        "rendered_prompt_token_count": 3719,
        "effective_temperature": 0,
    }
    right = {
        "engine": "omlx",
        "request": {**request, "portal_backend": "eval-b"},
        "outputs": [{"content": right_content}],
        "rendered_prompt_token_count": 3687,
        "effective_temperature": 0,
    }
    return left, right


def test_greedy_divergence_after_the_matched_prefix_is_recorded_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        runner, "parity_settings", lambda: {"prompt_token_tolerance": 0.02, "prefix_tokens": 2}
    )
    left, right = _drift_pair("OK the weather", "OK the weather in Boston is")

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is True
    assert result["classification"] == "greedy_numerical_drift"
    assert result["outputs_equal"] is False
    assert result["greedy_divergence"]["index"] == 3
    assert result["greedy_divergence"]["left_output"] == {"content": "OK the weather"}
    assert result["greedy_divergence"]["right_output"] == {"content": "OK the weather in Boston is"}
    assert result["prefix_tokens"] == 2


def test_greedy_divergence_before_the_matched_prefix_stays_invalid(monkeypatch) -> None:
    monkeypatch.setattr(
        runner, "parity_settings", lambda: {"prompt_token_tolerance": 0.02, "prefix_tokens": 2}
    )
    left, right = _drift_pair("Boston and clear", "OK the weather in Boston")

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is False
    assert result["classification"] == "greedy_output_mismatch_unexplained"
    assert result["greedy_divergence"]["index"] == 0
    assert "before the 2 the protocol requires to match" in result["findings"][-1]


def test_identical_greedy_outputs_still_report_a_match() -> None:
    left, right = _drift_pair("OK", "OK")

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is True
    assert result["classification"] == "match"
    assert result["greedy_divergence"]["identical"] is True


def test_candidate_parity_records_an_engine_that_drops_the_tool_schemas() -> None:
    request = {"messages": [{"role": "user", "content": "OK"}], "temperature": 0, "max_tokens": 64}
    left = {
        "engine": "mlx-serve",
        "request": {**request, "portal_backend": "eval-a"},
        "outputs": [{"content": "OK"}],
        "rendered_prompt_token_count": 219,
        "effective_temperature": 0,
        "tool_rendering": {
            "rendered": False,
            "with_tools_prompt_tokens": 219,
            "without_tools_prompt_tokens": 219,
        },
    }
    right = {
        "engine": "omlx",
        "request": {**request, "portal_backend": "eval-b"},
        "outputs": [{"content": "OK"}],
        "rendered_prompt_token_count": 219,
        "effective_temperature": 0,
    }

    comparison = runner._compare_candidate_parity(left, right)
    finding = runner._template_difference({"engine": "mlx-serve"}, comparison)

    assert comparison["classification"] == "tool_schema_not_rendered"
    assert "Tool-use quality is not comparable" in finding


def test_candidate_parity_records_greedy_nondeterminism_as_sampling_finding() -> None:
    parity = {
        "request": {
            "messages": [{"role": "user", "content": "OK"}],
            "temperature": 0,
            "max_tokens": 64,
        },
        "rendered_prompt_token_count": 12,
        "effective_temperature": 0,
    }
    left = {**parity, "outputs": [{"content": "A"}, {"content": "A"}]}
    right = {**parity, "outputs": [{"content": "A"}, {"content": "B"}]}

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is False
    assert result["classification"] == "sampling_or_nondeterminism"


def test_candidate_parity_reads_rendered_prompt_tokens_from_engine_logs() -> None:
    mlx_serve = runner._candidate_prompt_token_count("mlx-serve", "prompt=3506 tokens, max_gen=128")
    mlx_lm = runner._candidate_prompt_token_count(
        "mlx_lm.server", "Prompt processing progress: 2048/3490"
    )
    ctx = {
        "cell": {"engine": "mlx_lm.server"},
        "body": {"temperature": 0, "max_tokens": 128},
        "engine_log_text": "Prompt processing progress: 2048/3490",
        "prompt_blocks": runner._engine_prompt_blocks(
            "mlx_lm.server", "Prompt processing progress: 2048/3490"
        ),
        "log": "NON-STREAM tools: ['get_weather']",
        "parity_rows": [{"message": {"content": "OK"}}, {"message": {"content": "OK"}}],
    }
    evidence = runner._candidate_parity(ctx)

    assert mlx_serve == 3506
    assert mlx_lm == 3490
    assert evidence["requested_temperature"] == 0
    assert evidence["max_tokens"] == 128
    assert evidence["requests"] == [ctx["body"], ctx["body"]]
    assert evidence["outputs"] == [{"content": "OK"}, {"content": "OK"}]
    assert evidence["rendered_prompt_token_count"] == 3490
    assert evidence["effective_temperature"] is None
    assert evidence["tools_exposed"] == ["get_weather"]
    assert evidence["tool_rendering"]["rendered"] is None


def test_parity_prompt_count_comes_from_the_parity_request_not_the_preflight() -> None:
    """The preflight's no-tools request is logged first; its count is not the parity one."""
    log = "\n".join(
        [
            "POST /v1/chat/completions (2 msgs, max_tokens=128, temp=0.00, sys=869b, "
            "user=38b, tools=0b, tool_msgs=0)",
            "  prompt=219 tokens, max_gen=128, ctx=32768",
            "POST /v1/chat/completions (2 msgs, max_tokens=128, temp=0.00, sys=869b, "
            "user=72b, tools=9273b, tool_msgs=0)",
            "  prompt=3506 tokens, max_gen=128, ctx=32768",
            "POST /v1/chat/completions (2 msgs, max_tokens=128, temp=0.00, sys=869b, "
            "user=72b, tools=9273b, tool_msgs=0)",
            "  prompt=3506 tokens, max_gen=128, ctx=32768",
        ]
    )

    blocks = runner._engine_prompt_blocks("mlx-serve", log)

    assert runner._parity_prompt_tokens(blocks, user_bytes=len(runner.PARITY_PROMPT)) == 3506
    assert runner._tool_rendering(blocks)["rendered"] is True
    assert runner._tool_rendering(blocks)["without_tools_prompt_tokens"] == 219


def test_parity_prompt_count_is_unmeasured_when_the_log_has_no_parity_block() -> None:
    blocks = runner._engine_prompt_blocks("mlx-serve", "")

    assert runner._parity_prompt_tokens(blocks, user_bytes=72) is None
    assert runner._tool_rendering(blocks)["rendered"] is None


def test_candidate_memory_uses_engine_readback_after_first_completion(monkeypatch) -> None:
    cell = {
        "engine": "mlx-serve",
        "mode": "plain",
        "model": "m",
        "workspace": "w",
        "backend": "eval-a",
        "base": "http://127.0.0.1:11234",
        "port": 11234,
        "expected_model": "served-m",
    }
    events = []
    responses = iter(
        [
            {"status": 200, "json": {"data": [{"id": "/cache/served-m"}]}},
            {"status": 200, "json": {"data": [{"id": "served-m", "bytes_resident": 200}]}},
        ]
    )
    monkeypatch.setattr(
        runner.h2h, "load_config", lambda: {"models": {}, "engines": {"mlx-serve": {}}}
    )
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner, "_models_payload", lambda _base: next(responses))

    def fake_request(_url, _body):
        events.append("request")
        return {
            "header": "w;eval-a;served-m",
            "engine_model": "served-m",
            "text": "OK",
            "tokens": 1,
            "elapsed": 0.1,
            "message": {"content": "OK"},
        }

    def fake_memory(_vm_before, _port, _engine, _engine_cfg, model_row):
        events.append("memory")
        assert model_row["bytes_resident"] == 200
        return {"engine_weight_gb": 200 / 1024**3}

    monkeypatch.setattr(runner, "_candidate_request", fake_request)
    monkeypatch.setattr(runner, "_candidate_memory", fake_memory)
    monkeypatch.setattr(runner.instrument, "_pipeline_log_since", lambda _since: "")
    monkeypatch.setattr(
        runner.instrument,
        "grade_preflight",
        lambda _reply, _tool, served, **_kwargs: {"verdict": "OK", "served_model_id": served},
    )
    monkeypatch.setattr(runner, "_candidate_tokenizer", lambda _cfg, _cell: None)

    ctx = runner._candidate_cell_inputs(cell, "http://pipeline", vm_before="vm", resident_before={})

    assert events == ["request", "memory", "request", "request", "request"]
    assert ctx["memory_models_response"]["json"]["data"][0]["bytes_resident"] == 200
    assert ctx["preflight"]["served_model_id"] == "served-m"


def _parity_cell(engine: str = "mlx_lm.server") -> dict:
    return {
        "engine": engine,
        "mode": "plain",
        "seat": "daily-moe",
        "workspace": "bench-engine-daily-moe",
        "model": "m",
        "expected_model": "served-m",
        "backend": "eval-openai",
    }


def _parity_cfg() -> dict:
    return {
        "engines": {
            "mlx_lm.server": {"requires": "mlx"},
            "omlx": {"base": "http://127.0.0.1:8085"},
        },
        "models": {"m": {"mlx": "served-dir", "ollama": "tag"}},
    }


def _candidate_evidence(tokens: int = 3506, content: str = "OK") -> dict:
    body = {
        "messages": [{"role": "user", "content": "OK"}],
        "temperature": 0,
        "max_tokens": 128,
        "portal_backend": "eval-openai",
    }
    return {
        "template": {
            "same_checkpoint": True,
            "parity": {
                "requests": [body, body],
                "outputs": [{"content": content}, {"content": content}],
                "requested_temperature": 0,
                "max_tokens": 128,
                "rendered_prompt_token_count": tokens,
                "effective_temperature": None,
                "tools_exposed": ["get_weather"],
            },
        }
    }


def _incumbent(tokens: int, content: str = "OK") -> dict:
    return {
        "status": "measured",
        "engine": "omlx",
        "backend": runner.OMLX_INCUMBENT_BACKEND,
        "model": "served-m",
        "route": "bench-engine-daily-moe;eval-openai-omlx-incumbent;served-m",
        "engine_model": "served-m",
        "requests": [
            {
                "messages": [{"role": "user", "content": "OK"}],
                "temperature": 0,
                "max_tokens": 128,
                "portal_backend": runner.OMLX_INCUMBENT_BACKEND,
            }
        ],
        "outputs": [{"content": content}],
        "requested_temperature": 0,
        "max_tokens": 128,
        "effective_temperature": None,
        "rendered_prompt_token_count": tokens,
        "tools_exposed": ["get_weather"],
    }


def test_incumbent_parity_pairs_the_cell_with_omlx_inside_the_cell(monkeypatch) -> None:
    evidence = _candidate_evidence(3506)
    monkeypatch.setattr(runner, "_measure_incumbent_parity", lambda *args: _incumbent(3506))

    runner._attach_incumbent_parity(_parity_cell(), _parity_cfg(), "http://pipeline", evidence)

    template = evidence["template"]
    comparison = template["parity"]["comparisons"]["omlx"]
    assert template["parity"]["status"] == "compared"
    assert comparison["classification"] == "match"
    assert comparison["valid"] is True
    assert comparison["engines"] == {"left": "mlx_lm.server", "right": "omlx"}
    assert comparison["rendered_prompt_token_counts"] == {"left": 3506, "right": 3506}
    assert template["quality_comparable"] is True
    assert template.get("template_differs") is None
    assert "oMLX incumbent on the same checkpoint" in template["rule"]


def test_incumbent_parity_records_a_rendering_difference_as_a_finding(monkeypatch) -> None:
    evidence = _candidate_evidence(3100)
    monkeypatch.setattr(runner, "_measure_incumbent_parity", lambda *args: _incumbent(3506))

    runner._attach_incumbent_parity(_parity_cell(), _parity_cfg(), "http://pipeline", evidence)

    template = evidence["template"]
    comparison = template["parity"]["comparisons"]["omlx"]
    assert comparison["classification"] == "chat_template_rendering_mismatch"
    assert comparison["differs_from_incumbent"] == "left"
    assert template["quality_comparable"] is False
    assert "3100" in template["template_differs"] and "3506" in template["template_differs"]
    assert "-406" in template["template_differs"]
    assert template["reconciliation"]["available"] is False
    assert "chat_template.jinja" in template["reconciliation"]["detail"]


def test_incumbent_parity_is_unmeasured_when_the_reference_route_is_wrong(monkeypatch) -> None:
    evidence = _candidate_evidence()
    bad = {**_incumbent(3506), "status": "unmeasured", "reason": "incumbent route 'w;other;m'"}
    monkeypatch.setattr(runner, "_measure_incumbent_parity", lambda *args: bad)

    runner._attach_incumbent_parity(_parity_cell(), _parity_cfg(), "http://pipeline", evidence)

    template = evidence["template"]
    assert template["parity"]["status"] == "unmeasured"
    assert (
        template["parity"]["comparisons"]["omlx"]["classification"] == "incumbent_parity_unmeasured"
    )
    assert "incumbent route" in template["parity"]["comparisons"]["omlx"]["findings"][0]


def test_incumbent_parity_is_not_run_for_a_checkpoint_omlx_does_not_serve() -> None:
    evidence = _candidate_evidence()
    cfg = _parity_cfg()
    cfg["engines"]["gguf-llama"] = {"requires": "gguf"}

    runner._attach_incumbent_parity(
        {**_parity_cell(), "engine": "gguf-llama"}, cfg, "http://pipeline", evidence
    )

    template = evidence["template"]
    assert template["parity"]["status"] == "not_run"
    assert "does not load the MLX checkpoint" in template["parity"]["reason"]
    assert template["quality_comparable"] is True


def test_omlx_prompt_count_reads_the_server_log_per_request() -> None:
    log = (
        "Chat completion: model=other, 1 tokens in 0.1s, prompt: 30, finish_reason=stop\n"
        "Chat completion: model=served-m, 24 tokens in 4.0s (6.0 tok/s), prompt: 3506, "
        "finish_reason=tool_calls\n"
    )
    assert runner.omlx_prompt_token_count(log, "served-m") == 3506
    assert runner.omlx_prompt_token_count(log, "absent") is None


def test_pipeline_tools_exposed_reads_the_forwarded_schema_names() -> None:
    log = (
        "NON-STREAM tools: ['web_fetch', 'get_weather']\n"
        "NON-STREAM tools: ['web_fetch', 'get_weather']\n"
    )
    assert runner.pipeline_tools_exposed(log) == ["web_fetch", "get_weather"]
    assert runner.pipeline_tools_exposed("no tools line") is None


def test_stage3_marks_a_template_difference_quality_comparison_non_comparable() -> None:
    result = {
        "status": "PASS",
        "valid": True,
        "candidate_outcome": "PASS",
        "incumbent_outcome": "PASS",
    }
    canary = {"evidence": {"template": {"quality_comparable": False, "template_differs": "x"}}}

    runner._flag_non_comparable_quality(result, canary)

    assert result["not_comparable"] is True
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "quality non-comparable: x"
    assert runner._quality_not_worse(result) is None


def test_stage3_leaves_a_comparable_quality_result_alone() -> None:
    result = {"status": "PASS", "valid": True, "candidate_outcome": "PASS"}
    runner._flag_non_comparable_quality(
        result, {"evidence": {"template": {"quality_comparable": True}}}
    )
    assert result["status"] == "PASS"
    assert result.get("not_comparable") is None


def test_stage3_requires_a_valid_canary_for_this_build_and_cell(tmp_path: Path) -> None:
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
    }
    path = runner.canary_receipt_path(tmp_path, "build-a", cell)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"build": "build-a", "valid": True}), encoding="utf-8")

    assert runner.require_valid_canary(tmp_path, "build-a", cell)["valid"] is True
    with pytest.raises(runner.Stage3BlockedError, match="current build"):
        runner.require_valid_canary(tmp_path, "build-b", cell)

    path.write_text(json.dumps({"build": "build-a", "valid": False}), encoding="utf-8")
    with pytest.raises(runner.Stage3BlockedError, match="canary invalid"):
        runner.require_valid_canary(tmp_path, "build-a", cell)


def test_stage3_persists_block_receipt_for_protocol_mismatch(monkeypatch, tmp_path: Path) -> None:
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
    }
    canary_path = runner.canary_receipt_path(tmp_path, "build-a", cell)
    canary_path.parent.mkdir(parents=True)
    canary_path.write_text(
        json.dumps({"build": "build-a", "valid": True, "receipt": str(canary_path)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "protocol_issues", lambda: {"quality-seat": ["unmapped plan"]})

    result = runner.run_stage3(cell, "quality-seat")
    receipt = Path(result["receipt"])

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "unmapped plan"
    assert json.loads(receipt.read_text(encoding="utf-8")) == result


def test_failed_startup_is_recorded_with_logs_and_engine_models_body(monkeypatch, tmp_path: Path):
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
        "expected_model": "Qwen3.8-27B-4bit",
        "backend": "eval-openai-rapid-mlx",
        "port": 11235,
        "base": "http://127.0.0.1:11235",
        "launch_error": None,
        "argv": ["rapid-mlx"],
    }
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: (True, "ok"))
    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": 500})
    monkeypatch.setattr(
        runner,
        "_prepare_production_models",
        lambda _cfg: {"valid": True, "loaded": {}, "unloaded": {}, "remaining": {}, "failures": []},
    )
    monkeypatch.setattr(runner.h2h, "single_flight", nullcontext)
    monkeypatch.setattr(runner.h2h, "pid_on_port", lambda _port: None)
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_a, **_kw: "vm_stat")
    stopped = []
    monkeypatch.setattr(runner.h2h, "stop_managed", lambda _cfg, engine: stopped.append(engine))

    def fail_start(_cfg, _engine, _model, _mode, *, log_paths, on_started, **_kwargs):
        log_paths[0].write_text("startup stdout", encoding="utf-8")
        log_paths[1].write_text("invalid parser value", encoding="utf-8")
        on_started()
        raise SystemExit("engine process exited during startup (exit 2)")

    monkeypatch.setattr(runner.h2h, "start_managed", fail_start)
    monkeypatch.setattr(
        runner,
        "_models_payload",
        lambda _base: (_ for _ in ()).throw(runner.CandidateHTTPError(503, "still loading")),
    )

    receipt = runner.run_cell(cell, "http://pipeline")
    payload = json.loads(Path(receipt["receipt"]).read_text(encoding="utf-8"))

    assert receipt["valid"] is False
    assert "exit 2" in receipt["failures"][0]
    assert receipt["engine_models_response"]["status"] == 503
    assert receipt["engine_models_response"]["raw"] == "still loading"
    assert Path(receipt["engine_logs"]["stdout"]).read_text() == "startup stdout"
    assert Path(receipt["engine_logs"]["stderr"]).read_text() == "invalid parser value"
    assert payload["engine_logs"]["stderr"] == receipt["engine_logs"]["stderr"]
    assert stopped == ["rapid-mlx"]


def test_canary_continues_after_an_invalid_cell(monkeypatch, tmp_path: Path):
    cells = [
        {
            "engine": "rapid-mlx",
            "mode": "plain",
            "seat": "coding",
            "workspace": "bench-engine-coding",
            "model": "m1",
        },
        {
            "engine": "mlx-serve",
            "mode": "plain",
            "seat": "hunt",
            "workspace": "bench-engine-hunt",
            "model": "m2",
        },
    ]
    seen = []
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)

    def fake_run_cell(cell, _pipeline, build):
        seen.append(cell["engine"])
        return {
            "build": build,
            "cell": {key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")},
            "valid": cell["engine"] == "mlx-serve",
            "failures": [] if cell["engine"] == "mlx-serve" else ["startup exit 2"],
            "evidence_sources": {"logs": ["stdout.log", "stderr.log"]},
        }

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)
    results, exit_code = runner.run_canary("http://pipeline")

    assert seen == ["rapid-mlx", "mlx-serve"]
    assert [row["valid"] for row in results] == [False, True]
    assert exit_code == 2


def test_quality_plan_pins_same_model_to_omlx_incumbent_and_candidate(tmp_path: Path):
    cell = next(
        item
        for item in runner.candidate_cells()
        if item["seat"] == "daily-moe" and item["mode"] == "plain"
    )

    plan_path, source, _selections, plan = runner._wfe_plan(
        cell, tmp_path, "build-a", "quality-seat", compare=True
    )
    workload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))["workloads"][cell["workspace"]]
    incumbent = workload["arms"]["incumbent"]
    challenger = workload["arms"]["challengers"][0]

    assert source == "tests/wfe/plans/engine_h2h_202611_nemotron.yaml"
    assert workload["source_workspace"] == "auto-daily"
    assert incumbent["backend"] == "eval-openai-omlx-incumbent"
    assert incumbent["model"] == cell["expected_model"]
    assert challenger["backend"] == cell["backend"]
    assert challenger["model"] == cell["expected_model"]


def test_registered_protocol_has_no_unmapped_plan_or_seat_references():
    protocol = runner.yaml.safe_load(runner.PROTOCOL.read_text(encoding="utf-8"))
    plans = {
        plan
        for workload in protocol["workloads"]
        if workload["id"] == "quality-seat"
        for plan in workload["plans"]
    }

    assert not runner.protocol_issues()
    assert protocol["status"] == "APPROVED"
    assert protocol["approved_by"] == "operator"
    assert protocol["approved_on"].isoformat() == "2026-11-13"
    assert "coding_decision_v1" not in " ".join(sorted(plans))


def test_stage3_dispatches_after_canary_and_reuses_completed_receipt(monkeypatch, tmp_path: Path):
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
        "expected_model": "Qwen3.8-27B-4bit",
        "backend": "eval-openai-rapid-mlx",
        "port": 11235,
        "base": "http://127.0.0.1:11235",
        "launch_error": None,
        "argv": ["rapid-mlx"],
    }
    build = "build-a"
    canary_path = runner.canary_receipt_path(tmp_path, build, cell)
    canary_path.parent.mkdir(parents=True)
    canary_path.write_text(json.dumps({"build": build, "valid": True}), encoding="utf-8")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner, "current_build", lambda: build)
    calls = []
    monkeypatch.setattr(
        runner,
        "_run_long_context",
        lambda *args: calls.append(args) or {"status": "PASS", "valid": True},
    )

    first = runner.run_stage3(cell, "long-context", pipeline="http://pipeline")
    second = runner.run_stage3(cell, "long-context", pipeline="http://pipeline")

    assert first["status"] == "PASS"
    assert second == first
    assert len(calls) == 1


def test_stage0_prints_before_and_after_residency(monkeypatch, capsys) -> None:
    evidence = instrument.golden_evidence()
    evidence["residency"] = {
        "before": {"ollama": {}, "omlx": {}, "rapid-mlx": {"model": 123}},
        "after": {"ollama": {}, "omlx": {}, "rapid-mlx": {"model": 123}},
    }
    monkeypatch.setattr(instrument, "collect_stage0", lambda _spec, _pipeline: evidence)

    assert instrument.stage0(["--engine", "ollama", "--seat", "daily-moe"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["residency"] == evidence["residency"]


def test_raw_candidate_receipts_require_portal_data_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PORTAL_DATA_ROOT", raising=False)
    with pytest.raises(runner.Stage3BlockedError, match="PORTAL_DATA_ROOT"):
        runner.data_root()

    monkeypatch.setenv("PORTAL_DATA_ROOT", str(tmp_path))
    assert runner.data_root() == tmp_path


def _receipt(cell: dict, valid: bool, reason: str) -> dict:
    receipt = {
        "build": "build-a",
        "cell": {key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")},
        "valid": valid,
        "failures": [] if valid else [reason],
        "evidence_sources": {},
    }
    runner._stamp_reason(receipt)
    return receipt


def test_a_queued_omlx_unload_settles_instead_of_failing(monkeypatch, capsys) -> None:
    """oMLX 400s "Model not loaded" while its queued unload drains; it still releases."""
    loaded_reads = {"n": 0}

    def fake_http_json(url, payload=None, timeout=30):
        if url.endswith("/v1/models/status"):
            loaded_reads["n"] += 1
            loaded = loaded_reads["n"] == 1
            return {"models": [{"id": "loaded/model", "loaded": loaded, "actual_size": 10}]}
        if url.endswith("/api/ps"):
            return {"models": []}
        if url.endswith("/loaded%2Fmodel/unload"):
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", {}, io.BytesIO(b'{"detail":"Model not loaded"}')
            )
        raise AssertionError(url)

    monkeypatch.setattr(runner.h2h, "http_json", fake_http_json)
    cfg = {"engines": {"ollama": {"base": "http://o"}, "omlx": {"base": "http://m"}}}

    result = runner._prepare_production_models(cfg)

    assert result["valid"] is True
    assert result["unloaded"]["omlx"] == ["loaded/model"]
    assert result["remaining"]["omlx"] == []
    assert "unload already queued" in capsys.readouterr().out


def test_a_real_unload_refusal_is_still_a_failure(monkeypatch) -> None:
    def fake_http_json(url, payload=None, timeout=30):
        if url.endswith("/v1/models/status"):
            return {"models": [{"id": "busy/model", "loaded": True, "actual_size": 10}]}
        if url.endswith("/api/ps"):
            return {"models": []}
        if url.endswith("/busy%2Fmodel/unload"):
            raise urllib.error.HTTPError(
                url, 400, "Bad Request", {}, io.BytesIO(b'{"detail":"model has active requests"}')
            )
        raise AssertionError(url)

    monkeypatch.setattr(runner.h2h, "http_json", fake_http_json)

    result = runner._prepare_production_models(
        {"engines": {"ollama": {"base": "http://o"}, "omlx": {"base": "http://m"}}}
    )

    assert result["valid"] is False
    assert any("unload failed for busy/model" in item for item in result["failures"])


def test_every_stage3_engine_start_preps_the_host_first(monkeypatch, tmp_path: Path) -> None:
    order = []
    cell = {
        "engine": "mlx-serve",
        "engine_kind": "managed",
        "mode": "plain",
        "seat": "daily-moe",
        "workspace": "bench-engine-daily-moe",
        "model": "m",
        "port": 11234,
    }
    monkeypatch.setattr(runner.h2h, "load_config", lambda: {"engines": {}})
    monkeypatch.setattr(runner, "_gate_canary", lambda *_a: {})
    monkeypatch.setattr(runner.h2h, "pid_on_port", lambda _port: None)
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: (True, "ok"))
    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": 500})
    monkeypatch.setattr(runner.h2h, "single_flight", nullcontext)
    monkeypatch.setattr(
        runner,
        "_prepare_production_models",
        lambda _cfg: (
            order.append("prep")
            or {"valid": True, "unloaded": {"omlx": ["Qwen3.8-27B-4bit"], "ollama": []}}
        ),
    )

    def start(*_args, on_started=None, **_kwargs):
        order.append("start")
        if on_started:
            on_started()
        return {"ready_s": 1.0}

    monkeypatch.setattr(runner.h2h, "start_managed", start)
    monkeypatch.setattr(runner.h2h, "stop_managed", lambda *_a: order.append("stop"))

    with runner._running_cells([cell], tmp_path, "build-a") as (_infos, host_prep):
        assert host_prep["unloaded"]["omlx"] == ["Qwen3.8-27B-4bit"]

    assert order == ["prep", "start", "stop"]


def test_swap_start_refusal_restarts_only_the_two_approved_services(monkeypatch) -> None:
    readings = iter((5000, 3500))
    gates = iter(((False, "swap used 5000MB > 4096MB"), (True, "swap used 3500MB")))
    commands = []

    class Completed:
        returncode = 0
        stdout = "restarted"
        stderr = ""

    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": next(readings)})
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: next(gates))
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command) or Completed(),
    )
    monkeypatch.setattr(
        runner,
        "_wait_http_health",
        lambda url, _timeout: {"url": url, "healthy": True, "status": 200},
    )

    okay, reason, evidence = runner._start_gate_with_recovery({})

    uid = runner.os.getuid()
    assert okay is True
    assert reason == "swap used 3500MB"
    assert [command[-1] for command in commands] == [
        f"gui/{uid}/com.portal5.omlx",
        f"gui/{uid}/com.portal5.eg2-embedding",
    ]
    assert all(command[:3] == ["launchctl", "kickstart", "-k"] for command in commands)
    assert evidence["attempted"] is True
    assert evidence["swap_before_mb"] == 5000
    assert evidence["swap_after_mb"] == 3500
    assert set(evidence["health"]) == {label for label, _ in runner.SWAP_RECOVERY_SERVICES}


def test_swap_recovery_stops_when_gate_stays_refused_and_keeps_reading(monkeypatch) -> None:
    readings = iter((5200, 5300))
    gates = iter(((False, "swap used 5200MB > 4096MB"), (False, "swap used 5300MB > 4096MB")))

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": next(readings)})
    monkeypatch.setattr(runner.h2h, "start_gate", lambda _cfg: next(gates))
    monkeypatch.setattr(runner.subprocess, "run", lambda *_a, **_k: Completed())
    monkeypatch.setattr(
        runner,
        "_wait_http_health",
        lambda url, _timeout: {"url": url, "healthy": True, "status": 200},
    )

    okay, reason, evidence = runner._start_gate_with_recovery({})

    assert okay is False
    assert "swap used 5300MB" in reason
    assert evidence["swap_before_mb"] == 5200
    assert evidence["swap_after_mb"] == 5300


def test_a_failed_pre_workload_unload_refuses_to_start_the_engine(
    monkeypatch, tmp_path: Path
) -> None:
    cell = {
        "engine": "mlx-serve",
        "engine_kind": "managed",
        "mode": "plain",
        "seat": "daily-moe",
        "workspace": "bench-engine-daily-moe",
        "model": "m",
        "port": 11234,
    }
    started = []
    monkeypatch.setattr(runner.h2h, "load_config", lambda: {"engines": {}})
    monkeypatch.setattr(runner, "_gate_canary", lambda *_a: {})
    monkeypatch.setattr(runner.h2h, "pid_on_port", lambda _port: None)
    monkeypatch.setattr(
        runner,
        "_prepare_production_models",
        lambda _cfg: {"valid": False, "failures": ["omlx still has loaded model(s): ['m']"]},
    )
    monkeypatch.setattr(runner.h2h, "start_managed", lambda *_a, **_k: started.append("start"))

    with (
        pytest.raises(runner.Stage3BlockedError, match="pre-workload unload failed"),
        runner._running_cells([cell], tmp_path, "build-a"),
    ):
        pass

    assert started == []


def test_a_wfe_blocked_arm_reports_its_own_verdict_line() -> None:
    stdout = (
        "arm m@omlx-incumbent-1: BLOCKED — bench-engine-daily-moe: the build serving 'm' "
        "cannot be observed: backend 'eval-openai-omlx-incumbent' has no content identity\n\n"
        "campaign dir: /tmp/campaign\n"
    )
    detail = runner._wfe_failure_detail(stdout, "tool surface preflight: PASS (2 check(s))\n")
    assert detail.startswith("arm m@omlx-incumbent-1: BLOCKED")
    assert "content identity" in detail
    assert runner._wfe_failure_detail("", "tool surface preflight: PASS") == (
        "tool surface preflight: PASS"
    )


def test_missing_binary_is_the_absent_executable(tmp_path: Path) -> None:
    assert runner._missing_binary([str(tmp_path / "gone")], None) == str(tmp_path / "gone")
    exe = tmp_path / "present"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    assert runner._missing_binary([str(exe)], None) is None
    absent = "definitely-not-installed-engine-xyz"
    assert runner._missing_binary([absent], None) == absent


def test_a_not_installed_cell_is_skipped_and_does_not_stop_the_canary(
    monkeypatch, tmp_path: Path
) -> None:
    cells = [
        {
            "engine": "prismml-llama",
            "mode": "plain",
            "seat": "task-router",
            "workspace": "bench-engine-task-router",
            "model": "m",
            "not_installed": "prismml-llama not installed: /nope/llama-server is missing",
        },
        {"engine": "mlx-serve", "mode": "plain", "seat": "hunt", "workspace": "w", "model": "m"},
    ]
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    started = []

    def fake_run_cell(cell, _pipeline, build):
        started.append(cell["engine"])
        if cell.get("not_installed"):
            return {
                "build": build,
                "cell": {
                    key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")
                },
                "valid": False,
                "skipped": True,
                "status": "NOT_INSTALLED",
                "reason": cell["not_installed"],
                "failures": [],
            }
        return _receipt(cell, True, "ok")

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)

    results, code = runner.run_canary("http://pipeline")

    assert started == ["prismml-llama", "mlx-serve"]
    assert results[0]["skipped"] is True and results[1]["valid"] is True
    assert code == 0


def test_a_not_installed_cell_writes_a_skip_receipt_without_starting(
    monkeypatch, tmp_path: Path
) -> None:
    cell = {
        "engine": "prismml-llama",
        "mode": "plain",
        "seat": "task-router",
        "workspace": "bench-engine-task-router",
        "model": "m",
        "not_installed": "prismml-llama not installed: /nope/llama-server is missing",
    }
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner.h2h, "load_config", lambda: {"engines": {}})
    monkeypatch.setattr(runner.h2h, "start_managed", lambda *_a, **_k: pytest.fail("started"))

    receipt = runner.run_cell(cell, "http://pipeline")

    assert receipt["status"] == "NOT_INSTALLED"
    assert receipt["skipped"] is True and receipt["valid"] is False
    assert json.loads(Path(receipt["receipt"]).read_text(encoding="utf-8"))["skipped"] is True
    with pytest.raises(runner.Stage3BlockedError, match="not installed"):
        runner.require_valid_canary(tmp_path, runner.current_build(), cell)


def test_tokens_fall_back_to_the_engine_tokenizer_when_the_checkpoint_has_none(
    monkeypatch,
) -> None:
    ctx = {
        "cell": {"base": "http://engine"},
        "tokenizer": None,
        "think_row": {"text": "OK", "tokens": 2},
    }
    monkeypatch.setattr(runner, "_engine_token_count", lambda _cell, _text: 2)

    tokens = runner._token_evidence(ctx)

    assert tokens["engine_completion"] == 2
    assert tokens["tokenizer_completion"] == 2
    assert "/tokenize" in tokens["source"]


def test_tokens_prefer_the_checkpoint_tokenizer(monkeypatch, tmp_path: Path) -> None:
    tokenizer = tmp_path / "tokenizer.json"
    tokenizer.write_text("{}", encoding="utf-8")
    ctx = {
        "cell": {"base": "http://engine"},
        "tokenizer": tokenizer,
        "think_row": {"text": "OK", "tokens": 2},
    }
    monkeypatch.setattr(runner.instrument, "count_tokens", lambda _text, _path: 7)
    monkeypatch.setattr(runner, "_engine_token_count", lambda *_a: 99)

    tokens = runner._token_evidence(ctx)

    assert tokens["tokenizer_completion"] == 7
    assert "checkpoint tokenizer" in tokens["source"]


def test_engine_token_count_reads_the_tokenize_response(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"tokens": [1, 2, 3]}).encode()

    monkeypatch.setattr(runner.urllib.request, "urlopen", lambda *_a, **_k: Response())

    assert runner._engine_token_count({"base": "http://engine"}, "OK") == 3


def test_canary_cell_runs_one_cell_and_stops_on_two_consecutive_reasons(
    monkeypatch, tmp_path, capsys
):
    cells = [
        {"engine": "rapid-mlx", "mode": "plain", "seat": "coding", "workspace": "w", "model": "m"},
        {"engine": "rapid-mlx", "mode": "spec", "seat": "coding", "workspace": "w", "model": "m"},
        {
            "engine": "vllm-mlx",
            "mode": "plain",
            "seat": "daily-moe",
            "workspace": "w",
            "model": "m",
        },
    ]
    seen = []
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)

    def fake_run_cell(cell, _pipeline, build):
        seen.append(cell["engine"])
        return _receipt(
            cell, False, "pipeline did not report eval-openai-rapid-mlx healthy within 180s"
        )

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)
    _results, code = runner.run_canary("http://pipeline")
    assert seen == ["rapid-mlx", "rapid-mlx"]
    assert code == 2
    assert "2 consecutive cells" in capsys.readouterr().out

    seen.clear()
    one, code = runner.run_canary("http://pipeline", only="vllm-mlx:plain:daily-moe")
    assert seen == ["vllm-mlx"]
    assert len(one) == 1
    assert code == 2


def test_backend_health_reason_keeps_its_engine_so_engines_do_not_merge() -> None:
    """Two engines can 400 for different root causes; the normalised reason says which."""
    reason = (
        "candidate cell: HTTP 400: portal_backend: 'eval-openai-rapid-mlx' is not a healthy "
        "candidate backend for this workspace (healthy candidates: ['eval-openai-omlx-incumbent'])"
    )
    rapid = runner.normalise_reason(reason, {"engine": "rapid-mlx"})
    splash = runner.normalise_reason(reason, {"engine": "splash"})

    assert "engine=rapid-mlx" in rapid and "engine=splash" in splash
    assert rapid != splash
    assert "eval-openai-rapid-mlx" not in rapid  # ids still collapse for grouping
    assert runner.normalise_reason("startup exit 2", {"engine": "rapid-mlx"}) == "startup exit N"


def test_canary_does_not_stop_when_a_valid_cell_splits_the_same_reason(monkeypatch, tmp_path):
    cells = [
        {"engine": "a", "mode": "plain", "seat": "coding", "workspace": "w", "model": "m"},
        {"engine": "b", "mode": "plain", "seat": "hunt", "workspace": "w", "model": "m"},
        {"engine": "c", "mode": "plain", "seat": "daily-moe", "workspace": "w", "model": "m"},
    ]
    seen = []
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)

    def fake_run_cell(cell, _pipeline, build):
        seen.append(cell["engine"])
        return _receipt(cell, cell["engine"] == "b", "startup exit 2")

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)
    results, _code = runner.run_canary("http://pipeline")
    assert seen == ["a", "b", "c"]
    assert [row["valid"] for row in results] == [False, True, False]


def test_canary_stops_on_structural_readiness(monkeypatch, tmp_path):
    cells = [
        {
            "engine": "mlx_lm.server",
            "mode": "plain",
            "seat": "coding",
            "workspace": "w",
            "model": "m",
        },
        {"engine": "mlx-serve", "mode": "plain", "seat": "hunt", "workspace": "w", "model": "m"},
    ]
    seen = []
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)

    def fake_run_cell(cell, _pipeline, build):
        seen.append(cell["engine"])
        receipt = _receipt(cell, False, "structural readiness: listing has 4 other id(s)")
        return receipt

    monkeypatch.setattr(runner, "run_cell", fake_run_cell)
    results, code = runner.run_canary("http://pipeline")
    assert seen == ["mlx_lm.server"]
    assert results[0]["structural_readiness"] is True
    assert code == 2


def test_write_json_moves_an_existing_receipt_aside(tmp_path: Path) -> None:
    path = tmp_path / "cell.json"
    runner._write_json(path, {"valid": False, "reason": "first"})
    runner._write_json(path, {"valid": True, "reason": "ok"})
    backups = list(tmp_path.glob("cell.json.bak-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["reason"] == "first"
    assert json.loads(path.read_text(encoding="utf-8"))["reason"] == "ok"


def test_pipeline_health_wait_records_the_pipeline_body(monkeypatch) -> None:
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner.time, "monotonic", lambda: 0)
    monkeypatch.setattr(
        runner,
        "_pipeline_backend_list",
        lambda _pipeline: {"data": [{"id": "eval-openai-rapid-mlx", "healthy": False}]},
    )
    with pytest.raises(runner.Stage3BlockedError, match="eval-openai-rapid-mlx"):
        runner.wait_pipeline_eval_backend("http://pipeline", "eval-openai-rapid-mlx", timeout_s=0)


def test_stage3_plan_lists_only_valid_current_build_cells(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    cells = [
        {
            "engine": "rapid-mlx",
            "mode": "plain",
            "seat": "coding",
            "workspace": "bench-engine-coding",
            "model": "qwen38_27b_h2h",
            "engine_kind": "managed",
            "expected_model": "Qwen3.8-27B-4bit",
            "backend": "eval-openai-rapid-mlx",
            "port": 11235,
            "base": "http://127.0.0.1:11235",
        },
        {
            "engine": "mlx-serve",
            "mode": "plain",
            "seat": "coding",
            "workspace": "bench-engine-coding",
            "model": "qwen38_27b_h2h",
            "engine_kind": "managed",
            "expected_model": "Qwen3.8-27B-4bit",
            "backend": "eval-openai",
            "port": 11234,
            "base": "http://127.0.0.1:11234",
        },
    ]
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    good = runner.canary_receipt_path(tmp_path, "build-a", cells[0])
    good.parent.mkdir(parents=True)
    good.write_text(
        json.dumps({"build": "build-a", "valid": True, "cell": {"seat": "coding"}}),
        encoding="utf-8",
    )
    bad = runner.canary_receipt_path(tmp_path, "build-a", cells[1])
    bad.write_text(
        json.dumps({"build": "build-a", "valid": False, "cell": {"seat": "coding"}}),
        encoding="utf-8",
    )
    started = []
    monkeypatch.setattr(runner.h2h, "start_managed", lambda *_a, **_k: started.append("started"))

    plan = runner.build_stage3_plan("build-a")
    runner._print_plan(plan)

    engines = [entry["cell"]["engine"] for entry in plan["cells"]]
    assert engines == ["rapid-mlx", "omlx", "ollama"]
    assert plan["cells"][1]["cell"]["engine_kind"] == "external"
    assert plan["cells"][1]["cell"]["backend"] == "eval-openai-omlx-incumbent"
    assert plan["cells"][2]["cell"]["backend"] == "eval-openai-ollama-incumbent"
    assert "quality-seat" in plan["cells"][0]["workloads"]
    assert plan["estimate_s"] == 3 * sum(runner._WORKLOAD_ESTIMATE_S.values())
    assert started == []
    assert "upper bound" in capsys.readouterr().out

    bounded = runner.build_stage3_plan("build-a", seats=["coding"], skip_incumbents=("ollama",))
    bounded_engines = [entry["cell"]["engine"] for entry in bounded["cells"]]
    assert bounded_engines == ["rapid-mlx", "omlx"]
    assert bounded["seats"] == ["coding"]
    assert bounded["estimate_s"] == 2 * sum(runner._WORKLOAD_ESTIMATE_S.values())

    with pytest.raises(runner.Stage3BlockedError, match="no current-build valid canary cell"):
        runner.build_stage3_plan("build-a", seats=["hunt"])


def test_stage3_plan_runs_global_workload_phases_before_co_residence_and_soak(
    monkeypatch, tmp_path: Path
) -> None:
    cells = [
        {
            "engine": "mlx-serve",
            "mode": "plain",
            "seat": "daily-moe",
            "workspace": "bench-engine-daily-moe",
            "model": "daily-model",
        },
        {
            "engine": "rapid-mlx",
            "mode": "plain",
            "seat": "coding",
            "workspace": "bench-engine-coding",
            "model": "coding-model",
        },
    ]
    plan = {
        "build": "build-a",
        "cells": [
            {"role": "candidate", "cell": cell, "workloads": runner._plan_workloads()}
            for cell in cells
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner, "_notify", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_quiet_host_check", lambda: (None, None))
    monkeypatch.setattr(runner, "_eval_listeners", lambda: [])
    calls = []

    def run(cell, workload, **_kwargs):
        calls.append((workload, cell["seat"]))
        failed = workload == "co-residence" and cell["seat"] == "daily-moe"
        return {
            "build": "build-a",
            "cell_id": runner._cell_id(cell),
            "workload": workload,
            "status": "FAIL" if failed else "PASS",
            "valid": not failed,
            "failure_class": "workload_result" if failed else None,
            "reason": "cannot co-reside: engine refused prompt" if failed else "ok",
        }

    monkeypatch.setattr(runner, "run_stage3", run)

    code = runner.execute_stage3_plan(str(plan_path), "http://pipeline")

    assert code == 2
    assert calls == [
        *(("quality-seat", cell["seat"]) for cell in cells),
        *(("tool-turn", cell["seat"]) for cell in cells),
        *(("long-context", cell["seat"]) for cell in cells),
        *(("concurrency-mix", cell["seat"]) for cell in cells),
        *(("co-residence", cell["seat"]) for cell in cells),
        ("soak", "coding"),
    ]


def test_stage3_resume_reuses_completed_workload_failure_receipt(tmp_path: Path) -> None:
    cell = _seat_cell()
    row = {
        "build": "build-a",
        "cell_id": runner._cell_id(cell),
        "status": "FAIL",
        "valid": False,
        "failure_class": "workload_result",
        "reason": "cannot co-reside: engine refused",
    }
    path = runner._stage3_dir(tmp_path, "build-a") / f"{runner._cell_id(cell)}--co-residence.json"
    runner._write_json(path, row)

    assert runner._saved_stage3_workload(tmp_path, "build-a", cell, "co-residence") == row


def test_stage3_run_refuses_a_busy_host_and_skips_a_finished_cell(
    monkeypatch, tmp_path: Path
) -> None:
    cell = {
        "engine": "rapid-mlx",
        "mode": "plain",
        "seat": "coding",
        "workspace": "bench-engine-coding",
        "model": "qwen38_27b_h2h",
        "engine_kind": "managed",
        "expected_model": "Qwen3.8-27B-4bit",
        "backend": "eval-openai-rapid-mlx",
        "port": 11235,
        "base": "http://127.0.0.1:11235",
    }
    plan = {
        "build": "build-a",
        "cells": [
            {"role": "candidate", "cell": cell, "workloads": ["quality-seat"], "estimate_s": 1}
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(runner, "data_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "current_build", lambda: "build-a")
    monkeypatch.setattr(runner, "_configure_results", lambda _root: None)
    monkeypatch.setattr(runner, "_notify", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_eval_listeners", lambda: [])
    monkeypatch.setattr(runner, "_quiet_host_check", lambda: ("dispatch lane job: 99", None))
    called = []
    monkeypatch.setattr(runner, "run_stage3", lambda *_a, **_k: called.append("ran"))

    code = runner.execute_stage3_plan(str(plan_path), "http://pipeline")
    assert code == 2
    assert called == []
    receipt = json.loads(
        runner._cell_summary_path(tmp_path, "build-a", cell).read_text(encoding="utf-8")
    )
    assert receipt["reason"] == "dispatch lane job: 99"
    assert receipt["finished"] is False

    code_again = runner.execute_stage3_plan(str(plan_path), "http://pipeline")
    assert called == []
    assert code_again == 2


def test_matrix_verdict_stays_unproven_without_speed() -> None:
    result = {
        "cell": {"engine": "rapid-mlx", "mode": "plain", "seat": "coding"},
        "workloads": {
            "quality-seat": {
                "candidate_outcome": "PASS",
                "incumbent_outcome": "PASS",
                "valid": True,
            },
            "co-residence": {"valid": True, "status": "PASS"},
            "soak": {"valid": True, "status": "PASS"},
        },
    }
    assert runner._matrix_verdict(result) == "Unproven — keep the incumbent"


def _tool_call_message(content: str = "", arguments: str = '{"city":"Boston"}') -> dict:
    return {
        "content": content,
        "tool_calls": [
            {"type": "function", "function": {"name": "get_weather", "arguments": arguments}}
        ],
    }


def test_preflight_sends_think_off_without_tools_and_a_separate_forced_call(monkeypatch) -> None:
    cell = {
        "engine": "mlx-serve",
        "mode": "plain",
        "seat": "daily-moe",
        "workspace": "bench-engine-daily-moe",
        "model": "m",
        "backend": "eval-openai",
        "base": "http://127.0.0.1:11234",
        "port": 11234,
        "expected_model": "served-m",
    }
    sent: list[dict] = []

    def fake_request(_url: str, body: dict) -> dict:
        sent.append(dict(body))
        message = _tool_call_message() if body.get("tool_choice") else {"content": "OK\n\n"}
        return {
            "header": "w;eval-openai;served-m",
            "engine_model": "served-m",
            "text": "OK",
            "tokens": 2,
            "elapsed": 0.1,
            "message": message,
        }

    monkeypatch.setattr(
        runner.h2h, "load_config", lambda: {"models": {}, "engines": {"mlx-serve": {}}}
    )
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner, "_models_payload", lambda _base: {"status": 200, "json": {}})
    monkeypatch.setattr(runner, "_model_row", lambda _payload, _model: {})
    monkeypatch.setattr(runner, "_candidate_request", fake_request)
    monkeypatch.setattr(runner, "_candidate_tokenizer", lambda _cfg, _cell: None)
    monkeypatch.setattr(runner.instrument, "_pipeline_log_since", lambda _since: "")
    monkeypatch.setattr(
        runner.instrument,
        "grade_preflight",
        lambda reply, tool, served, **_kwargs: {
            "verdict": "OK",
            "think_off_reply": reply,
            "tool_call": tool,
        },
    )

    ctx = runner._candidate_cell_inputs(cell, "http://pipeline", vm_before="vm", resident_before={})

    think_off, tool_call, parity_a, parity_b = sent
    assert think_off["tools"] == [] and "tool_choice" not in think_off
    assert think_off["messages"][0]["content"] == runner.THINK_OFF_PROMPT
    assert tool_call["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}
    assert tool_call["tools"] == runner.instrument._TOOL_SPEC
    assert parity_a == parity_b
    assert parity_a["tool_choice"]["function"]["name"] == "get_weather"
    assert len(ctx["parity_rows"]) == 2
    assert ctx["preflight"]["separate_requests"] is True


def test_prose_under_a_forced_choice_is_recorded_as_not_honoured() -> None:
    row = {"message": _tool_call_message(content="OK\n\n")}

    honoured = runner._forced_tool_choice("mlx_lm.server", row)
    suppressed = runner._forced_tool_choice("mlx-serve", {"message": _tool_call_message()})

    assert honoured["honoured"] is False
    assert "prose" in honoured["evidence"]
    assert "mlx_lm/server.py" in honoured["evidence"]
    assert suppressed["honoured"] is True
    assert suppressed["rule"] == runner.FORCED_CHOICE_RULE


def _seat_cell(**overrides) -> dict:
    cell = {
        "engine": "mlx-serve",
        "mode": "plain",
        "seat": "daily-moe",
        "workspace": "bench-engine-daily-moe",
        "expected_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
        "backend": "eval-openai",
        "port": 11234,
        "base": "http://engine",
    }
    cell.update(overrides)
    return cell


def test_co_residence_takes_its_swap_baseline_after_host_prep(monkeypatch) -> None:
    """Growth must measure the co-resident engines, not the unload that preceded them."""
    order: list[str] = []
    prep = {"valid": True, "unloaded": {"omlx": ["resident/model"], "ollama": []}}
    monkeypatch.setattr(
        runner.h2h,
        "load_config",
        lambda: {
            "engines": {},
            "guard": {"max_start_swap_used_mb": 4096, "max_swap_growth_mb": 2048},
        },
    )

    def other_seat(seat, *_args):
        return {
            "seat": seat,
            "workspace": f"bench-engine-{seat}",
            "engine": seat,
            "port": 2000,
            "backend": f"eval-openai-{seat}",
            "expected_model": "m",
            "base": "http://engine",
        }

    monkeypatch.setattr(runner, "_valid_cell_for_seat", other_seat)
    monkeypatch.setattr(runner, "_prepare_host", lambda _cfg: order.append("prep") or prep)
    swaps = {"n": 0}

    def swap_now():
        swaps["n"] += 1
        order.append(f"swap{swaps['n']}")
        return {"used_mb": 100 + swaps["n"]}

    monkeypatch.setattr(runner.h2h, "swap_now", swap_now)
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_a, **_k: "vm_stat")
    seen: dict = {}

    def request(target, _pipeline, _messages, **_extra):
        return {
            "workspace": target["workspace"],
            "backend": target["backend"],
            "expected_model": target["expected_model"],
            "engine_model": target["expected_model"],
            "route": f"{target['workspace']};{target['backend']};{target['expected_model']}",
            "text": "OK",
            "elapsed_s": 0.1,
        }

    monkeypatch.setattr(runner, "_pipeline_request", request)

    @contextlib.contextmanager
    def fake_running(cells, _root, _build, context_tokens=None, host_prep=None):
        seen["order_at_start"] = list(order)
        seen["host_prep"] = host_prep
        yield {}, host_prep

    monkeypatch.setattr(runner, "_running_cells", fake_running)
    cell = _seat_cell()

    result = runner._run_co_residence(cell, Path("."), "build-a", "http://pipeline")

    assert seen["order_at_start"] == ["prep", "swap1"]
    assert seen["host_prep"] is prep
    assert result["swap_before_mb"] == 101
    assert result["swap_after_mb"] == 102
    assert result["swap_growth_mb"] == 1
    assert result["host_prep"] is prep
    assert result["valid"] is True


def test_co_residence_engine_refusal_is_a_failed_result_with_the_engine_message(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        runner.h2h,
        "load_config",
        lambda: {
            "engines": {},
            "guard": {"max_start_swap_used_mb": 4096, "max_swap_growth_mb": 2048},
        },
    )
    monkeypatch.setattr(
        runner,
        "_valid_cell_for_seat",
        lambda seat, *_a: {
            "engine": f"engine-{seat}",
            "seat": seat,
            "workspace": f"bench-engine-{seat}",
            "port": 11235,
            "backend": f"eval-openai-{seat}",
            "expected_model": f"model-{seat}",
            "base": "http://engine",
        },
    )
    monkeypatch.setattr(runner, "_prepare_host", lambda _cfg: {"valid": True})
    monkeypatch.setattr(runner, "_candidate_residency", lambda _cfg: {})
    monkeypatch.setattr(runner.subprocess, "check_output", lambda *_a, **_k: "vm_stat")
    monkeypatch.setattr(runner.instrument, "vm_deltas_gb", lambda *_a: {})
    readings = iter((100, 180))
    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": next(readings)})
    requested = []

    def request(target, *_args, **_kwargs):
        requested.append(target["seat"])
        if target["seat"] == "daily-moe":
            raise runner.CandidateHTTPError(507, "prompt needs 2692 MB; 135 MB free")
        return {
            "workspace": target["workspace"],
            "backend": target["backend"],
            "expected_model": target["expected_model"],
            "route": f"{target['workspace']};{target['backend']};{target['expected_model']}",
            "engine_model": target["expected_model"],
            "text": "OK",
            "elapsed_s": 0.1,
        }

    monkeypatch.setattr(runner, "_pipeline_request", request)

    @contextlib.contextmanager
    def fake_running(_cells, _root, _build, context_tokens=None, host_prep=None):
        yield {}, host_prep

    monkeypatch.setattr(runner, "_running_cells", fake_running)
    result = runner._run_co_residence(_seat_cell(), Path("."), "build-a", "http://pipeline")

    assert result["status"] == "FAIL"
    assert result["valid"] is False
    assert result["failure_class"] == "workload_result"
    runner._stamp_outcome(result)
    assert result["verdict"] == "fail"
    assert "cannot co-reside" in result["reason"]
    assert "prompt needs 2692 MB; 135 MB free" in result["reason"]
    assert "growth=80MB" in result["reason"]
    assert requested == ["daily-moe"]
    assert "swap_stop" not in result
    repeated = {**result, "reason_norm": runner.normalise_reason(result["reason"], _seat_cell())}
    result["reason_norm"] = repeated["reason_norm"]
    assert runner._cells_should_stop([result, repeated]) is None


def test_long_context_window_resolves_every_protocol_seat() -> None:
    assert runner._long_context_tokens(_seat_cell()) == 32768
    assert (
        runner._long_context_tokens(_seat_cell(seat="coding", workspace="bench-engine-coding"))
        == 98304
    )
    assert (
        runner._long_context_tokens(
            _seat_cell(seat="council-json", workspace="bench-engine-council-json")
        )
        == 32768
    )
    assert runner._long_context_tokens({"seat": "daily-moe"}) == 32768
    assert (
        runner._long_context_tokens(_seat_cell(seat="hunt", workspace="bench-engine-hunt")) is None
    )


def test_long_context_daily_moe_receipt_uses_integer_prefill_bound(monkeypatch) -> None:
    cell = _seat_cell(model="nemotron_35_lightning")
    monkeypatch.setattr(runner.h2h, "load_config", lambda: {})
    monkeypatch.setattr(runner, "_candidate_tokenizer", lambda *_args: Path("tokenizer.json"))
    monkeypatch.setattr(instrument, "count_tokens", lambda _text, _tokenizer: 30000)
    monkeypatch.setattr(runner, "_models_payload", lambda _base: {"json": {}})
    monkeypatch.setattr(runner, "_context_readback", lambda *_args: {"context_length": 32768})
    monkeypatch.setattr(
        runner,
        "_running_cells",
        lambda *_args, **_kwargs: nullcontext(([], {"valid": True})),
    )

    def answer_from_needle(_url, request, _headers):
        prompt = request["messages"][0]["content"]
        return {"text": prompt.split("Needle record: ", 1)[1].split()[0]}

    monkeypatch.setattr(instrument, "_one_chat", answer_from_needle)

    result = runner._run_long_context(cell, Path("."), "build-a", "http://pipeline")

    assert result["context_tokens"] == 32768
    assert result["valid"] is True


def _mix_target() -> dict:
    return {
        "workspace": "bench-engine-hunt",
        "backend": "eval-openai-vllm-mlx",
        "expected_model": "gemma-4-26b-a4b-it-QAT-4bit",
    }


def test_hunt_json_mix_opts_out_of_workspace_tools(monkeypatch) -> None:
    seen: dict = {}

    def capture(target, _pipeline, _messages, **extra):
        seen["extra"] = extra
        return {
            "text": '{"ok": true, "slot": "json-0"}',
            "workspace": target["workspace"],
            "backend": target["backend"],
            "expected_model": target["expected_model"],
            "engine_model": target["expected_model"],
            "route": f"{target['workspace']};{target['backend']};{target['expected_model']}",
        }

    monkeypatch.setattr(runner, "_pipeline_request", capture)

    row = runner._mix_request(_mix_target(), "http://pipeline", "json-0", True)

    assert seen["extra"] == {"response_format": {"type": "json_object"}, "tools": []}
    assert row["valid"] is True


def test_chat_mix_matches_auto_daily_and_does_not_set_response_format(monkeypatch) -> None:
    seen: dict = {}

    def capture(target, _pipeline, _messages, **extra):
        seen["extra"] = extra
        return {
            "text": "OK",
            "workspace": target["workspace"],
            "backend": target["backend"],
            "expected_model": target["expected_model"],
            "engine_model": target["expected_model"],
            "route": f"{target['workspace']};{target['backend']};{target['expected_model']}",
        }

    monkeypatch.setattr(runner, "_pipeline_request", capture)
    target = {**_mix_target(), "workspace": "bench-engine-daily-moe"}

    row = runner._mix_request(target, "http://pipeline", "chat-0", False)

    assert seen["extra"] == {}
    assert row["valid"] is True


def test_mix_http_rejection_is_a_failed_row_not_a_crash(monkeypatch) -> None:
    def reject(*_args, **_kwargs):
        raise runner.CandidateHTTPError(400, "tools and response_format cannot be combined")

    monkeypatch.setattr(runner, "_pipeline_request", reject)

    row = runner._mix_request(_mix_target(), "http://pipeline", "json-0", True)

    assert row["valid"] is False
    assert row["upstream_http"]["status"] == 400
    assert "cannot be combined" in row["reason"]
    assert row["elapsed_s"] >= 0


def test_concurrency_failure_reason_names_request_route_quality_and_latency() -> None:
    row = {
        "label": "json-5",
        "workspace": "bench-engine-hunt",
        "backend": "eval-openai-vllm-mlx",
        "expected_model": "gemma-QAT",
        "route": "bench-engine-hunt;wrong-backend;other-model",
        "engine_model": "other-model",
        "json_valid": False,
        "text": '{"ok": false, "slot": "json-4"}',
        "elapsed_s": 0.427,
    }

    reason = runner._mix_failure_detail(row)

    assert "json-5" in reason
    assert "wrong-backend" in reason and "gemma-QAT" in reason
    assert "JSON quality mismatch" in reason and "json-4" in reason
    assert "latency=0.427s" in reason


def test_workload_swap_growth_over_the_protocol_limit_fails_and_stops(monkeypatch) -> None:
    monkeypatch.setattr(
        runner.h2h,
        "load_config",
        lambda: {"guard": {"max_swap_growth_mb": 2048}},
    )
    monkeypatch.setattr(runner.h2h, "swap_now", lambda: {"used_mb": 7480})
    result = {"valid": True, "status": "PASS", "reason": "status PASS"}

    runner._record_workload_swap(result, 1900)

    assert result["valid"] is False
    assert result["status"] == "FAIL"
    assert result["swap_stop"] is True
    assert result["swap_before_mb"] == 1900
    assert result["swap_after_mb"] == 7480
    assert result["swap_growth_mb"] == 5580
    assert "5580MB" in result["reason"]
    assert "status PASS" in result["reason"]


def test_summary_prints_pending_when_the_incumbent_has_not_run() -> None:
    rows = runner._summary_rows(
        [
            {
                "cell": {"engine": "mlx-serve", "mode": "plain", "seat": "daily-moe"},
                "workloads": {},
            }
        ]
    )

    assert rows[0]["incumbent"] == "pending"
    assert rows[0]["candidate"] == "mlx-serve:plain:daily-moe"


def test_staged_cell_stops_after_a_workload_grows_swap(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake(_cell, name, build=None, pipeline=""):
        calls.append(name)
        if name == "long-context":
            return {
                "valid": False,
                "status": "FAIL",
                "reason": "swap grew 5580MB (before 1900MB, after 7480MB) > 2048MB",
                "swap_gate": False,
                "swap_stop": True,
            }
        return {"valid": True, "status": "PASS", "reason": "ok"}

    monkeypatch.setattr(runner, "run_stage3", fake)

    receipt = runner._run_staged_cell(_seat_cell(), tmp_path, "build-a", "http://pipeline")

    assert calls == ["quality-seat", "tool-turn", "long-context"]
    assert receipt["swap_stop"] is True


def test_a_missing_forced_call_fails_the_tool_call_check() -> None:
    graded = runner._grade_cell_preflight(
        _seat_cell(),
        {
            "message": {"content": "OK\n\n"},
            "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
        },
        {
            "message": {"content": "OK\n\n"},
            "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
        },
    )

    assert graded["verdict"] == "REVIEW"
    assert graded["tool_choice"]["honoured"] is False
    assert "no valid get_weather call" in graded["tool_choice"]["evidence"]


def test_a_workspace_without_tools_excludes_the_tool_half_instead_of_failing() -> None:
    """The Pipeline strips tools for bench-engine-task-router; the engine is not graded on it."""
    model = "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"
    row = {"message": {"content": "OK"}, "engine_model": model}

    graded = runner._grade_cell_preflight(
        _seat_cell(seat="task-router", workspace="bench-engine-task-router", expected_model=model),
        row,
        {"message": {"content": "OK"}, "engine_model": model},
    )

    assert graded["verdict"] == "OK"
    assert graded["tool_call"]["decision"] == "exclude"
    assert graded["tool_call"]["applicable"] is False
    assert "bench-engine-task-router declares no tools" in graded["tool_call"]["reason"]
    assert graded["tool_choice"]["applicable"] is False
    assert graded["think_off_reply"] == "OK"


def test_a_model_declared_without_tool_support_excludes_the_tool_half() -> None:
    model = "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"
    row = {"message": {"content": "OK"}, "engine_model": model}

    graded = runner._grade_cell_preflight(
        _seat_cell(expected_model=model),
        row,
        {"message": {"content": "OK"}, "engine_model": model},
    )

    assert graded["verdict"] == "OK"
    assert "supports_tools: false" in graded["tool_call"]["reason"]


def test_the_think_off_half_still_applies_when_tools_are_excluded() -> None:
    model = "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"
    graded = runner._grade_cell_preflight(
        _seat_cell(seat="task-router", workspace="bench-engine-task-router", expected_model=model),
        {"message": {"content": "hello"}, "engine_model": model},
        {"message": {"content": "hello"}, "engine_model": model},
    )

    assert graded["verdict"] == "REVIEW"
    assert graded["tool_call"]["decision"] == "exclude"


def test_tool_turn_is_not_applicable_when_the_seat_cannot_take_tools(monkeypatch) -> None:
    monkeypatch.setattr(runner, "protocol_issues", lambda: {})
    monkeypatch.setattr(runner, "_workspace_tools", lambda _workspace: ())
    monkeypatch.setattr(
        runner, "_run_quality_workload", lambda *_a, **_k: pytest.fail("workload ran")
    )

    result = runner._execute_stage3_workload(
        _seat_cell(), "tool-turn", Path("."), "build-a", "http://pipeline"
    )

    assert result["status"] == "NOT_APPLICABLE"
    assert result["valid"] is True
    assert "declares no tools" in result["reason"]


def test_tool_turn_still_runs_for_a_tool_capable_seat(monkeypatch) -> None:
    monkeypatch.setattr(runner, "protocol_issues", lambda: {})
    calls = []
    monkeypatch.setattr(
        runner,
        "_run_tool_turn",
        lambda *args: calls.append(args) or {"valid": True},
    )

    result = runner._execute_stage3_workload(
        _seat_cell(), "tool-turn", Path("."), "build-a", "http://pipeline"
    )

    assert result == {"valid": True}
    assert calls


@contextlib.contextmanager
def _fake_running_cells(*_args, **_kwargs):
    yield [], {"valid": True}


def _tool_turn_messages(answer: str) -> list[dict]:
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "get_weather", "arguments": '{"city": "Boston"}'},
    }
    return [
        {
            "header": "bench-engine-daily-moe;eval-openai;NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
            "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
            "message": {"content": "", "tool_calls": [call]},
        },
        {
            "header": "bench-engine-daily-moe;eval-openai;NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
            "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
            "message": {"content": answer},
        },
    ]


def test_tool_turn_passes_on_a_call_and_a_post_tool_answer(monkeypatch) -> None:
    monkeypatch.setattr(runner, "_running_cells", _fake_running_cells)
    responses = iter(_tool_turn_messages("The tool reported 18C and clear."))
    monkeypatch.setattr(runner, "_candidate_request", lambda _url, _body: next(responses))

    result = runner._run_tool_turn(_seat_cell(), Path("."), "build-a", "http://pipeline")

    assert result["valid"] is True
    assert result["verdict"] == "pass"
    assert result["tool_calls"] == 1
    assert result["turns"] == 2
    assert "post-tool turn used its result" in result["reason"]
    assert result["requests"][1]["messages"][2]["role"] == "tool"


def test_tool_turn_fails_with_a_reason_when_no_tool_call_comes_back(monkeypatch) -> None:
    monkeypatch.setattr(runner, "_running_cells", _fake_running_cells)
    responses = iter(
        [
            {
                "header": "bench-engine-daily-moe;eval-openai;NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
                "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
                "message": {"content": "I cannot call tools."},
            },
            {
                "header": "bench-engine-daily-moe;eval-openai;NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
                "engine_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp",
                "message": {"content": "no answer"},
            },
        ]
    )
    monkeypatch.setattr(runner, "_candidate_request", lambda _url, _body: next(responses))

    result = runner._run_tool_turn(_seat_cell(), Path("."), "build-a", "http://pipeline")

    assert result["valid"] is False
    assert result["verdict"] == "fail"
    assert result["reason"].startswith("tool turn: no usable get_weather call")


def test_tool_turn_fails_when_the_post_tool_answer_ignores_the_result(monkeypatch) -> None:
    monkeypatch.setattr(runner, "_running_cells", _fake_running_cells)
    responses = iter(_tool_turn_messages("I do not know the temperature."))
    monkeypatch.setattr(runner, "_candidate_request", lambda _url, _body: next(responses))

    result = runner._run_tool_turn(_seat_cell(), Path("."), "build-a", "http://pipeline")

    assert result["valid"] is False
    assert "did not use the tool result" in result["reason"]


def test_a_receipt_without_a_reason_still_carries_one_and_a_verdict() -> None:
    result = {"status": "FAIL", "valid": False, "tool_calls": 0, "turns": 2, "tool_errors": 0}

    runner._stamp_outcome(result)

    assert result["verdict"] == "fail"
    assert result["reason"] == "status FAIL, tool_calls=0, turns=2, tool_errors=0"
