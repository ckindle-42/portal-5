"""Offline contracts for the candidate engine-evaluation runner."""

from __future__ import annotations

import json
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
        "rendered_prompt_token_count": 3490,
        "effective_temperature": None,
        "effective_temperature_note": "engine log has no effective sampling readback",
    }

    result = runner._compare_candidate_parity(left, right)

    assert result["valid"] is False
    assert result["classification"] == "chat_template_rendering_mismatch"
    assert result["rendered_prompt_token_counts"] == {"left": 3506, "right": 3490}
    assert "effective sampling readback" in result["findings"][0]


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
        "rows": [{"message": {"content": "OK"}}, {"message": {"content": "OK"}}],
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
        lambda _reply, _tool, served: {"verdict": "OK", "served_model_id": served},
    )
    monkeypatch.setattr(runner, "_candidate_tokenizer", lambda _cfg, _cell: None)

    ctx = runner._candidate_cell_inputs(cell, "http://pipeline", vm_before="vm", resident_before={})

    assert events == ["request", "memory", "request"]
    assert ctx["memory_models_response"]["json"]["data"][0]["bytes_resident"] == 200
    assert ctx["preflight"]["served_model_id"] == "served-m"


def test_canary_pair_reconciliation_updates_both_same_checkpoint_receipts(
    monkeypatch, tmp_path: Path
) -> None:
    cells = [
        {
            "engine": "mlx-serve",
            "mode": "plain",
            "seat": "daily-moe",
            "workspace": "w",
            "model": "m",
        },
        {
            "engine": "mlx_lm.server",
            "mode": "plain",
            "seat": "daily-moe",
            "workspace": "w",
            "model": "m",
        },
    ]
    monkeypatch.setattr(runner, "candidate_cells", lambda: cells)
    monkeypatch.setattr(
        runner.instrument,
        "judge_cell",
        lambda evidence: {
            "valid": all(
                comparison.get("valid") is True
                for comparison in evidence["template"]["parity"]["comparisons"].values()
            ),
            "failures": ["template: paired greedy parity failed"]
            if any(
                comparison.get("valid") is not True
                for comparison in evidence["template"]["parity"]["comparisons"].values()
            )
            else [],
        },
    )
    paths = []
    for cell, tokens in zip(cells, (3506, 3490), strict=True):
        path = runner.canary_receipt_path(tmp_path, "build-a", cell)
        path.parent.mkdir(parents=True, exist_ok=True)
        parity = {
            "requests": [{"temperature": 0, "max_tokens": 128}],
            "outputs": [{"content": "OK"}, {"content": "OK"}],
            "requested_temperature": 0,
            "max_tokens": 128,
            "rendered_prompt_token_count": tokens,
            "effective_temperature": 0 if cell["engine"] == "mlx-serve" else None,
        }
        receipt = {
            "build": "build-a",
            "cell": cell,
            "valid": False,
            "failures": ["template: paired greedy parity is pending"],
            "evidence": {"template": {"same_checkpoint": True, "parity": parity}},
        }
        path.write_text(json.dumps(receipt), encoding="utf-8")
        paths.append(path)

    result = runner._reconcile_candidate_parity(
        tmp_path, "build-a", [json.loads(paths[1].read_text(encoding="utf-8"))]
    )
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in paths]

    assert (
        result[0]["evidence"]["template"]["parity"]["comparisons"]["mlx-serve"]["classification"]
        == "chat_template_rendering_mismatch"
    )
    assert (
        receipts[0]["evidence"]["template"]["parity"]["comparisons"]["mlx_lm.server"]["valid"]
        is False
    )
    assert (
        receipts[1]["evidence"]["template"]["parity"]["comparisons"]["mlx-serve"]["valid"] is False
    )


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


def test_canary_cell_runs_one_cell_and_stops_on_two_consecutive_reasons(
    monkeypatch, tmp_path, capsys
):
    cells = [
        {"engine": "rapid-mlx", "mode": "plain", "seat": "coding", "workspace": "w", "model": "m"},
        {"engine": "mlx-serve", "mode": "plain", "seat": "hunt", "workspace": "w", "model": "m"},
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
    assert seen == ["rapid-mlx", "mlx-serve"]
    assert code == 2
    assert "2 consecutive cells" in capsys.readouterr().out

    seen.clear()
    one, code = runner.run_canary("http://pipeline", only="vllm-mlx:plain:daily-moe")
    assert seen == ["vllm-mlx"]
    assert len(one) == 1
    assert code == 2


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
    monkeypatch.setattr(runner, "quiet_host_refusal", lambda: "dispatch lane job: 99")
    called = []
    monkeypatch.setattr(runner, "run_stage3", lambda *_a, **_k: called.append("ran"))

    code = runner.execute_stage3_plan(str(plan_path), "http://pipeline")
    assert code == 2
    assert called == []
    receipt = json.loads(
        runner._cell_summary_path(tmp_path, "build-a", cell).read_text(encoding="utf-8")
    )
    assert receipt["reason"] == "dispatch lane job: 99"
    assert receipt["finished"] is True

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
