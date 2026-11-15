"""Offline contracts for the production-fit gate (engine_prodfit)."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from tests.benchmarks import engine_eval_runner as runner
from tests.benchmarks import engine_prodfit as prodfit


def _cell(selector: str = "mlx-serve:plain:coding") -> dict[str, Any]:
    # CI has no engine binaries; the run-path tests judge the gate, not the install probe.
    return {**runner.prodfit_cell(selector), "not_installed": None}


def _ctx(tmp_path: Path, selector: str = "mlx-serve:plain:coding") -> dict[str, Any]:
    ctx = prodfit._context(_cell(selector), "http://127.0.0.1:9099", "build123", tmp_path)
    ctx["pipeline_backend"] = {"ready": True, "backend": {"id": ctx["cell"]["backend"]}}
    ctx["pre_candidate"] = {
        "valid": True,
        "stack": {"valid": True, "down": [], "services": []},
        "warm": [],
        "loaded": {"missing": []},
    }
    return ctx


def _host(swap: float = 1000.0, pressure: int = 1) -> dict[str, Any]:
    return {
        "vm_wired_gb": 20.0,
        "vm_free_gb": 8.0,
        "vm_stat": {
            "page_bytes": 16384,
            "wired_pages": 20 * 65536,
            "free_pages": 8 * 65536,
        },
        "swap_used_mb": swap,
        "memory_free_pct": 40.0,
        "pressure_level": pressure,
        "at": "now",
    }


def _snapshot(swap: float = 1000.0, pid: int | None = 4242, pressure: int = 1) -> dict[str, Any]:
    return {
        "at": "now",
        "host": _host(swap, pressure),
        "omlx": {"status": 200, "loaded": {}, "models": []},
        "ollama": {"status": 200, "loaded": []},
        "load_plan": {"status": 200, "plan": {"fits": True}},
        "budget": {"budget_source": "omlx final_ceiling (LOAD_GUARD_CEILING_GB unset)"},
        "guard_metrics": {"status": 200, "series": {}},
        "candidate_pid": pid,
    }


def _ok_row(**extra: Any) -> dict[str, Any]:
    return {
        "status": 200,
        "answered": True,
        "text": "OK",
        "elapsed_s": 1.0,
        "route": "ws;backend;model",
        **extra,
    }


def _item_ok(name: str) -> dict[str, Any]:
    return {"item": name, "status": "PASS", "valid": True, "checks": {}, "evidence": {}}


def test_prodfit_config_reads_the_registry_block() -> None:
    block = prodfit.prodfit_config()
    assert set(block["production_seats"]) == {"daily-moe", "coding", "hunt"}
    assert block["production_seats"]["coding"]["production_route"]["backend"] == "omlx-coding"
    assert block["concurrency"] == 2
    assert block["autoupdate_channels"]["mlx-serve"]["channel"].startswith("brew")


def test_prodfit_config_refuses_a_missing_block() -> None:
    with pytest.raises(prodfit.ProdfitBlockedError):
        prodfit.prodfit_config({"engines": {}})


def test_context_keeps_the_other_two_production_seats(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "mlx-serve:plain:coding")
    assert [target["seat"] for target in ctx["others"]] == ["daily-moe", "hunt"]
    assert ctx["seat_is_production"] is True
    assert ctx["receipt"] == tmp_path / "engine_eval" / "prodfit" / "build123" / (
        "mlx-serve--plain--coding.json"
    )


def test_context_for_a_non_production_seat_keeps_all_three(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, "mlx-serve:plain:task-router")
    assert [target["seat"] for target in ctx["others"]] == ["daily-moe", "coding", "hunt"]
    assert ctx["seat_is_production"] is False


def test_swap_gate_uses_the_runner_guard(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    before = {"host": _host(1000.0)}
    after = {"host": _host(1500.0)}
    gate = prodfit._swap_gate(ctx, before, after)
    assert gate["valid"] is True
    assert gate["swap_growth_mb"] == 500.0
    over = prodfit._swap_gate(ctx, before, {"host": _host(4000.0)})
    assert over["valid"] is False
    assert any("swap grew" in reason for reason in over["reasons"])


def test_co_residence_passes_beside_two_production_seats(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit, "_missing_seats", lambda _seats, _cfg: {"state": {"loaded": {}}, "missing": []}
    )
    snapshots = iter([_snapshot(1000.0), _snapshot(1200.0)])
    monkeypatch.setattr(prodfit, "_snapshot", lambda _ctx, _seats: next(snapshots))
    monkeypatch.setattr(
        prodfit,
        "_seat_request",
        lambda workspace, backend, _p, phase: _ok_row(
            workspace=workspace, backend=backend, phase=phase
        ),
    )
    monkeypatch.setattr(
        prodfit,
        "_candidate_row",
        lambda _ctx, phase: _ok_row(ok=True, pinned_route_ok=True, phase=phase),
    )
    monkeypatch.setattr(
        prodfit,
        "_concurrent_candidate_rows",
        lambda _ctx, workers: [_ok_row(ok=True, pinned_route_ok=True) for _ in range(workers)],
    )
    monkeypatch.setattr(prodfit, "_candidate_log_text", lambda _ctx: "")

    item = prodfit._co_residence(ctx)

    assert item["status"] == "PASS"
    assert item["checks"]["no_production_eviction"]["pass"] is True
    assert item["checks"]["swap_gate"]["pass"] is True
    assert len(item["evidence"]["candidate_requests"]) == 3
    assert item["warnings"] == []


def test_co_residence_fails_when_a_production_seat_is_evicted(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit,
        "_missing_seats",
        lambda _s, _c: {"state": {}, "missing": ["gemma-4-26b-a4b-it-QAT-4bit"]},
    )
    snapshots = iter([_snapshot(1000.0), _snapshot(1100.0)])
    monkeypatch.setattr(prodfit, "_snapshot", lambda _ctx, _seats: next(snapshots))
    monkeypatch.setattr(
        prodfit,
        "_seat_request",
        lambda ws, backend, _p, phase: _ok_row(workspace=ws, backend=backend),
    )
    monkeypatch.setattr(
        prodfit, "_candidate_row", lambda _ctx, _phase: _ok_row(ok=True, pinned_route_ok=True)
    )
    monkeypatch.setattr(
        prodfit,
        "_concurrent_candidate_rows",
        lambda _ctx, workers: [_ok_row(ok=True, pinned_route_ok=True)],
    )
    monkeypatch.setattr(prodfit, "_candidate_log_text", lambda _ctx: "")

    item = prodfit._co_residence(ctx)

    assert item["status"] == "FAIL"
    assert item["checks"]["no_production_eviction"]["pass"] is False
    assert item["reason"] == "failed: no_production_eviction"


def test_co_residence_refuses_to_judge_with_the_stack_down(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    ctx["pre_candidate"]["stack"] = {
        "valid": False,
        "down": ["eg2-embedding"],
        "services": [],
    }
    item = prodfit._co_residence(ctx)
    assert item["status"] == "FAIL"
    assert "eg2-embedding" in str(item["reason"])


def test_co_residence_warns_on_critical_pressure_and_oom(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(prodfit, "_missing_seats", lambda _s, _c: {"state": {}, "missing": []})
    snapshots = iter([_snapshot(1000.0), _snapshot(1100.0, pressure=4)])
    monkeypatch.setattr(prodfit, "_snapshot", lambda _ctx, _seats: next(snapshots))
    monkeypatch.setattr(
        prodfit,
        "_seat_request",
        lambda ws, backend, _p, phase: _ok_row(workspace=ws, backend=backend),
    )
    monkeypatch.setattr(
        prodfit, "_candidate_row", lambda _ctx, _phase: _ok_row(ok=True, pinned_route_ok=True)
    )
    monkeypatch.setattr(
        prodfit,
        "_concurrent_candidate_rows",
        lambda _ctx, workers: [_ok_row(ok=True, pinned_route_ok=True)],
    )
    monkeypatch.setattr(prodfit, "_candidate_log_text", lambda _ctx: "error: out of memory")

    item = prodfit._co_residence(ctx)

    assert any("critical" in warning for warning in item["warnings"])
    assert any("memory exhaustion" in warning for warning in item["warnings"])


def test_lifecycle_records_stop_cold_load_and_downtime_answer(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit,
        "_stop_candidate",
        lambda _ctx: {"stop_s": 1.5, "port": 11234, "port_free": True, "listener": None},
    )
    monkeypatch.setattr(
        prodfit,
        "_down_probes",
        lambda _ctx: {
            "production_route": {"ok": True, "status": 200},
            "ollama_fallback": {"ok": True, "status": 200},
            "exclusive_workspace": {"ok": False, "status": 400, "definite": True},
        },
    )
    monkeypatch.setattr(
        prodfit, "_start_candidate", lambda _ctx: {"ready_s": 96.4, "pid": 999, "argv": []}
    )
    monkeypatch.setattr(
        prodfit,
        "_candidate_row",
        lambda _ctx, phase: {"ok": True, "elapsed_s": 0.75, "phase": phase},
    )

    item = prodfit._lifecycle(ctx)

    assert item["status"] == "PASS"
    assert item["evidence"]["cold_load_s"] == 96.4
    assert item["evidence"]["stop"]["stop_s"] == 1.5
    assert item["evidence"]["incumbent_control"]["unload"].startswith("POST /admin/api/models")


def test_lifecycle_does_not_fail_a_non_production_seat_for_a_missing_route(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "mlx-serve:plain:task-router")
    monkeypatch.setattr(
        prodfit,
        "_stop_candidate",
        lambda _ctx: {"stop_s": 1.0, "port_free": True, "listener": None},
    )
    monkeypatch.setattr(
        prodfit,
        "_down_probes",
        lambda _ctx: {"exclusive_workspace": {"ok": False, "status": 400, "definite": True}},
    )
    monkeypatch.setattr(prodfit, "_start_candidate", lambda _ctx: {"ready_s": 30.0})
    monkeypatch.setattr(prodfit, "_candidate_row", lambda _ctx, phase: {"ok": True})

    item = prodfit._lifecycle(ctx)

    assert item["status"] == "PASS"
    assert (
        item["checks"]["production_route_answers_while_down"]["not_applicable"]
        == "task-router is not a production seat; no production route to check"
    )


def test_guard_metrics_parse_and_delta(monkeypatch) -> None:
    text = (
        "# HELP portal5_load_guard_admissions_total admissions\n"
        'portal5_load_guard_admissions_total{engine="omlx"} 7.0\n'
        'portal5_load_guard_unloads_total{engine="omlx",reason="idle_omlx"} 2.0\n'
        "portal5_load_guard_headroom_bytes 123.0\n"
    )
    monkeypatch.setattr(prodfit, "_get_text", lambda *_a, **_k: {"status": 200, "text": text})
    before = prodfit._guard_metrics("http://127.0.0.1:9099")
    assert before["series"]['portal5_load_guard_admissions_total{engine="omlx"}'] == 7.0
    after = {
        "series": {
            **before["series"],
            'portal5_load_guard_unloads_total{engine="omlx",reason="idle_omlx"}': 3.0,
        }
    }
    delta = prodfit._guard_delta(before, after)
    assert delta == {'portal5_load_guard_unloads_total{engine="omlx",reason="idle_omlx"}': 1.0}


def test_down_probes_reuse_the_production_route_when_it_is_the_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path, "mlx-serve:plain:daily-moe")
    calls: list[str] = []
    monkeypatch.setattr(
        prodfit,
        "_seat_request",
        lambda ws, backend, _p, phase: (
            calls.append(phase) or _ok_row(workspace=ws, backend=backend)
        ),
    )
    rows = prodfit._down_probes(ctx)
    assert calls == ["down-production", "down-exclusive"]
    assert "already is its Ollama fallback" in rows["ollama_fallback"]["note"]


def test_pipeline_sees_backend_waits_for_the_pipeline_health_record(monkeypatch) -> None:
    calls: list[str] = []

    def fake_http(url: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(url)
        rows = [] if len(calls) == 1 else [{"id": "eval-openai", "healthy": True}]
        return {"status": 200, "json": {"data": rows}, "headers": {}, "error": None}

    monkeypatch.setattr(prodfit, "_http", fake_http)
    monkeypatch.setattr(prodfit.time, "sleep", lambda _s: None)
    seen = prodfit._pipeline_sees_backend("http://127.0.0.1:9099", "eval-openai")
    assert seen["ready"] is True
    assert len(calls) == 2


def test_pipeline_sees_backend_times_out_with_the_pipeline_answer(monkeypatch) -> None:
    monkeypatch.setattr(
        prodfit,
        "_http",
        lambda *_a, **_k: {"status": 200, "json": {"data": []}, "headers": {}, "error": None},
    )
    seen = prodfit._pipeline_sees_backend("http://127.0.0.1:9099", "eval-openai", timeout_s=0)
    assert seen["ready"] is False
    assert seen["last"] == {"data": []}


def test_pinned_route_ok_reads_the_engine_that_answered() -> None:
    cell = _cell()
    assert prodfit._pinned_route_ok(
        {"route": f"{cell['workspace']};{cell['backend']};different-model"}, cell
    )
    assert not prodfit._pinned_route_ok(
        {"route": f"{cell['workspace']};ollama-general;{cell['expected_model']}"}, cell
    )
    assert not prodfit._pinned_route_ok({"route": ""}, cell)


def test_health_check_accepts_a_declared_cache_listing(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit,
        "_http",
        lambda *_a, **_k: {
            "status": 200,
            "json": {"data": [{"id": "other"}]},
            "headers": {},
            "error": None,
        },
    )
    entry = {"health_path": "/v1/models", "listing_is_served_set": False}
    item = prodfit._health_check(ctx, entry)
    assert item["status"] == "PASS"
    assert (
        item["checks"]["seat_id_resolves_or_listing_not_served_set"]["listing_resolves_seat"]
        is False
    )


def test_health_check_fails_when_the_listing_is_the_served_set_and_misses(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit,
        "_http",
        lambda *_a, **_k: {
            "status": 200,
            "json": {"data": [{"id": "other"}]},
            "headers": {},
            "error": None,
        },
    )
    item = prodfit._health_check(ctx, {"health_path": "/v1/models"})
    assert item["status"] == "FAIL"


def test_version_check_needs_a_probe_and_a_declared_channel(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit.h2h,
        "engine_identity",
        lambda _cfg, _engine, _argv: {"ok": True, "installed": "26.11.2", "reason": None},
    )
    item = prodfit._version_check(ctx, {"id": "eval-openai"})
    assert item["status"] == "PASS"
    assert item["evidence"]["engine_autoupdate_covered"] is False
    monkeypatch.setattr(
        prodfit.h2h,
        "engine_identity",
        lambda _cfg, _engine, _argv: {"ok": True, "installed": None, "reason": None},
    )
    assert prodfit._version_check(ctx, None)["status"] == "FAIL"


def test_arch_check_reads_the_running_executable(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit, "_resolve_program", lambda _argv, _cwd: {"path": "/bin/echo", "error": None}
    )
    monkeypatch.setattr(
        prodfit, "_running_executable", lambda _port: {"pid": 77, "executable": "/bin/echo"}
    )
    monkeypatch.setattr(prodfit, "_command", lambda *_a, **_k: "Mach-O 64-bit executable arm64")
    monkeypatch.setattr(prodfit.platform, "machine", lambda: "arm64")
    item = prodfit._arch_check(ctx)
    assert item["status"] == "PASS"
    assert item["evidence"]["running"]["pid"] == 77
    monkeypatch.setattr(prodfit, "_command", lambda *_a, **_k: "Mach-O 64-bit executable x86_64")
    assert prodfit._arch_check(ctx)["status"] == "FAIL"


def test_arch_check_follows_a_shell_wrapper_to_its_interpreter(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit, "_running_executable", lambda _port: {"pid": 9, "executable": "/opt/x/libexec/py"}
    )
    monkeypatch.setattr(
        prodfit,
        "_resolve_program",
        lambda _argv, _cwd: {"path": "/opt/x/bin/engine", "error": None},
    )
    chains = {
        "/opt/x/bin/engine": [
            {"path": "/opt/x/bin/engine", "file": "POSIX shell script text executable"},
            {"path": "/opt/x/libexec/python", "file": "Mach-O 64-bit executable arm64"},
        ],
        "/opt/x/libexec/py": [{"path": "/opt/x/libexec/py", "file": "Mach-O universal binary"}],
    }
    monkeypatch.setattr(prodfit, "_launch_chain", lambda program: chains.get(program, []))
    monkeypatch.setattr(prodfit.platform, "machine", lambda: "arm64")
    item = prodfit._arch_check(ctx)
    assert item["status"] == "PASS"
    assert len(item["checks"]["launcher_arm64"]["readings"]) == 2


def test_arch_check_refuses_to_claim_an_engine_that_is_not_running(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit, "_running_executable", lambda _port: {"pid": None, "executable": None}
    )
    monkeypatch.setattr(
        prodfit, "_resolve_program", lambda _argv, _cwd: {"path": "/bin/echo", "error": None}
    )
    monkeypatch.setattr(prodfit, "_command", lambda *_a, **_k: "Mach-O 64-bit executable arm64")
    monkeypatch.setattr(prodfit.platform, "machine", lambda: "arm64")
    item = prodfit._arch_check(ctx)
    assert item["status"] == "FAIL"
    assert item["checks"]["launcher_arm64"]["pass"] is True
    assert item["checks"]["engine_executable_arm64"]["pass"] is False


def test_config_check_matches_the_registry_port_and_models(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    entry = prodfit._backend_entry(ctx)
    item = prodfit._config_check(ctx, entry)
    assert item["status"] == "PASS"
    ctx["cell"]["port"] = 11999
    assert prodfit._config_check(ctx, entry)["status"] == "FAIL"


def test_launchd_check_writes_and_lints_a_keepalive_plist(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        prodfit, "_resolve_program", lambda _argv, _cwd: {"path": "/bin/echo", "error": None}
    )
    monkeypatch.setattr(prodfit, "_command", lambda *_a, **_k: "")
    item = prodfit._launchd_check(ctx)
    assert item["status"] == "PASS"
    path = Path(item["evidence"]["plist"])
    assert path.is_file()
    assert item["evidence"]["plist_body"]["KeepAlive"] is True
    assert item["evidence"]["plist_body"]["ProgramArguments"][0] == "/bin/echo"


def test_launchd_check_refuses_an_unrendered_placeholder(tmp_path: Path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    ctx["cell"]["argv"] = ["/bin/echo", "--model", "{model_dir}"]
    monkeypatch.setattr(
        prodfit, "_resolve_program", lambda _argv, _cwd: {"path": "/bin/echo", "error": None}
    )
    monkeypatch.setattr(prodfit, "_command", lambda *_a, **_k: "")
    item = prodfit._launchd_check(ctx)
    assert item["status"] == "FAIL"
    assert item["checks"]["argv_rendered"]["unrendered"] == ["{model_dir}"]


def test_safe_step_turns_a_refusal_into_a_failed_item(tmp_path: Path) -> None:
    def boom(_ctx: dict[str, Any]) -> dict[str, Any]:
        raise prodfit.ProdfitBlockedError("port busy")

    item = prodfit._safe_step(boom, _ctx(tmp_path))
    assert item["valid"] is False
    assert "port busy" in item["reason"]


def _warm_stub() -> dict[str, Any]:
    return {
        "valid": True,
        "stack": {"valid": True, "down": [], "services": []},
        "warm": [],
        "loaded": {"missing": []},
    }


def test_run_prodfit_writes_the_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(prodfit.h2h, "single_flight", lambda: nullcontext())
    monkeypatch.setattr(prodfit, "_warm_production", lambda _ctx: _warm_stub())
    monkeypatch.setattr(prodfit, "_start_candidate", lambda _ctx: {"pid": 5, "ready_s": 10.0})
    monkeypatch.setattr(prodfit, "_co_residence", lambda _ctx: _item_ok("co-residence"))
    monkeypatch.setattr(prodfit, "_operations", lambda _ctx: _item_ok("operations"))
    monkeypatch.setattr(prodfit, "_lifecycle", lambda _ctx: _item_ok("lifecycle"))
    monkeypatch.setattr(prodfit, "_ensure_stopped", lambda _ctx: {"port_free": True})

    receipt = prodfit.run_prodfit(_cell(), "http://127.0.0.1:9099", build="abc123", root=tmp_path)

    assert receipt["verdict"] == "PASS"
    path = tmp_path / "engine_eval" / "prodfit" / "abc123" / "mlx-serve--plain--coding.json"
    assert path.is_file()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["build"] == "abc123"
    assert written["other_production_seats"][0]["seat"] == "daily-moe"
    assert set(written) >= {"co_residence", "lifecycle", "operations", "shutdown"}


def test_run_prodfit_fails_the_verdict_when_one_item_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(prodfit.h2h, "single_flight", lambda: nullcontext())
    monkeypatch.setattr(prodfit, "_warm_production", lambda _ctx: _warm_stub())
    monkeypatch.setattr(prodfit, "_start_candidate", lambda _ctx: {"pid": 5})
    failed = {**_item_ok("co-residence"), "status": "FAIL", "valid": False}
    monkeypatch.setattr(prodfit, "_co_residence", lambda _ctx: failed)
    monkeypatch.setattr(prodfit, "_operations", lambda _ctx: _item_ok("operations"))
    monkeypatch.setattr(prodfit, "_lifecycle", lambda _ctx: _item_ok("lifecycle"))
    monkeypatch.setattr(prodfit, "_ensure_stopped", lambda _ctx: {"port_free": True})

    receipt = prodfit.run_prodfit(_cell(), "http://127.0.0.1:9099", build="b", root=tmp_path)

    assert receipt["verdict"] == "FAIL"
    assert receipt["failed_items"] == ["co_residence"]


def test_run_prodfit_writes_a_blocked_receipt_for_an_uninstalled_cell(tmp_path: Path) -> None:
    cell = {**_cell(), "not_installed": "mlx-serve missing"}
    receipt = prodfit.run_prodfit(cell, "http://127.0.0.1:9099", build="b", root=tmp_path)
    assert receipt["verdict"] == "BLOCKED"
    assert "mlx-serve missing" in receipt["reason"]
    assert Path(receipt["receipt"]).is_file()


def test_cli_rejects_a_bad_cell_selector(capsys) -> None:
    code = runner.main(["prodfit", "--cell", "mlx-serve:coding"])
    assert code == 2
    assert "engine:mode:seat" in capsys.readouterr().out


def test_cli_prodfit_writes_under_portal_data_root(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("PORTAL_DATA_ROOT", str(tmp_path))
    seen: dict[str, Any] = {}

    def fake_run(cell: dict[str, Any], pipeline: str, **kwargs: Any) -> dict[str, Any]:
        seen.update({"cell": cell["seat"], "pipeline": pipeline, **kwargs})
        return {
            "cell_id": "mlx-serve--plain--coding",
            "verdict": "PASS",
            "failed_items": [],
            "receipt": str(tmp_path / "r.json"),
        }

    monkeypatch.setattr(prodfit, "run_prodfit", fake_run)
    code = runner.main(["prodfit", "--cell", "mlx-serve:plain:coding", "--build", "deadbeef"])
    assert code == 0
    assert seen["cell"] == "coding"
    assert seen["build"] == "deadbeef"
    assert seen["root"] == tmp_path.resolve()
    capsys.readouterr()
