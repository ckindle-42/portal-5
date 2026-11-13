#!/usr/bin/env python3
"""Run managed engine-eval canaries and guard Stage 3 receipts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from tests.benchmarks import bench_engine_h2h as h2h
from tests.benchmarks import engine_eval_instrument as instrument

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("engine_eval_protocol_20261113.yaml")
OPENAI_MODELS_SOURCE = "https://platform.openai.com/docs/api-reference/models/list"
OPENAI_CHAT_SOURCE = "https://platform.openai.com/docs/api-reference/chat/create"


class Stage3BlockedError(RuntimeError):
    """A required gate or protocol mapping does not support this run."""


def data_root() -> Path:
    """Return the required external evidence directory."""
    raw = os.environ.get("PORTAL_DATA_ROOT")
    if not raw:
        raise Stage3BlockedError("PORTAL_DATA_ROOT is required for raw engine-eval output")
    root = Path(raw).expanduser().resolve()
    if root == REPO or REPO in root.parents:
        raise Stage3BlockedError("PORTAL_DATA_ROOT must be outside the repository")
    return root


def _configure_results(root: Path) -> None:
    """Move the existing harness state and logs below PORTAL_DATA_ROOT."""
    h2h.RESULTS = root / "tests" / "benchmarks" / "results" / "engine_h2h"
    h2h.STATE_DIR = h2h.RESULTS / "state"


def _bench_workspaces() -> dict[str, Any]:
    path = REPO / "config" / "bench_workspaces.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("workspaces") or {}


def _cell_id(cell: dict[str, Any]) -> str:
    return "--".join(str(cell[key]) for key in ("engine", "mode", "seat"))


def canary_receipt_path(root: Path, build: str, cell: dict[str, Any]) -> Path:
    """Path to one immutable canary receipt for a commit and cell."""
    return root / "engine_eval" / "canaries" / build / f"{_cell_id(cell)}.json"


def require_valid_canary(root: Path, build: str, cell: dict[str, Any]) -> dict[str, Any]:
    """Read a cell receipt, refusing missing, stale, or invalid evidence."""
    path = canary_receipt_path(root, build, cell)
    if not path.is_file():
        raise Stage3BlockedError(f"no canary receipt for {_cell_id(cell)} on current build {build}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("build") != build:
        raise Stage3BlockedError(
            f"canary receipt for {_cell_id(cell)} is not for the current build"
        )
    if receipt.get("valid") is not True:
        raise Stage3BlockedError(f"canary invalid for {_cell_id(cell)}: {receipt.get('failures')}")
    return receipt


def current_build() -> str:
    """Return the lane HEAD used to key the canary gate."""
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, timeout=10
    ).strip()


def candidate_cells() -> list[dict[str, Any]]:
    """Expand approved seats over managed registry engines and declared modes."""
    cfg = h2h.load_config()
    workspaces = _bench_workspaces()
    matrix = cfg.get("engine_eval") or {}
    excluded = {
        (item["seat"], item["engine"], item["mode"]): item["reason"]
        for item in matrix.get("excluded_cells") or []
    }
    cells = []
    for seat, mapping in (matrix.get("seats") or {}).items():
        workspace = mapping["workspace"]
        workspace_cfg = workspaces[workspace]
        model = mapping["model"]
        hint = str(workspace_cfg["model_hint"])
        for engine, engine_cfg in cfg["engines"].items():
            if engine_cfg.get("kind") != "managed" or not h2h.model_supports_engine(
                cfg, model, engine
            ):
                continue
            modes = ["plain"]
            if h2h.spec_entry(cfg, model, engine) is not None:
                modes.append("spec")
            for mode in modes:
                if (seat, engine, mode) in excluded:
                    continue
                cells.append(
                    _make_cell(cfg, engine, engine_cfg, mode, seat, mapping, workspace_cfg, hint)
                )
    return cells


def _make_cell(
    cfg: dict,
    engine: str,
    engine_cfg: dict,
    mode: str,
    seat: str,
    mapping: dict,
    workspace_cfg: dict,
    hint: str,
) -> dict[str, Any]:
    """Resolve the process argv and static route identity for one cell."""
    model = mapping["model"]
    try:
        argv, cwd = h2h.launch_command(cfg, engine, model, mode)
        launch_error = None
    except SystemExit as exc:
        argv, cwd, launch_error = [], None, str(exc)
    engine_cfg = cfg["engines"][engine]
    port = int(engine_cfg["port"])
    return {
        "seat": seat,
        "workspace": mapping["workspace"],
        "engine": engine,
        "engine_kind": engine_cfg["kind"],
        "mode": mode,
        "model": model,
        "model_hint": hint,
        "expected_model": hint,
        "backend": "eval-openai" if port == 11234 else f"eval-openai-{engine}",
        "port": port,
        "base": h2h.base_url(cfg, engine),
        "argv": argv,
        "cwd": cwd,
        "launch_error": launch_error,
        "workspace_settings": workspace_cfg,
    }


def _candidate_residency(cfg: dict) -> dict[str, dict[str, int] | None]:
    """Capture loaded model identities from both production engines and all ports."""
    residents = {
        name: instrument._resident_snapshot(name, h2h.base_url(cfg, name))
        for name in ("ollama", "omlx")
    }
    for engine, entry in cfg["engines"].items():
        if entry.get("kind") != "managed":
            continue
        pid = h2h.pid_on_port(int(entry["port"]))
        if not pid:
            residents[engine] = {}
            continue
        state_file = h2h._state_file(engine)
        if not state_file.is_file():
            residents[engine] = {f"listener:{pid}": pid}
            continue
        state = json.loads(state_file.read_text(encoding="utf-8"))
        model = state.get("model")
        mode = state.get("mode", "plain")
        try:
            served = h2h.served_id(cfg, engine, model, mode) if model else f"listener:{pid}"
        except (KeyError, SystemExit):
            served = f"listener:{pid}"
        residents[engine] = {str(served): pid}
    return residents


def _candidate_memory(vm_before: str, port: int) -> dict[str, Any]:
    """Read OS residency without treating process RSS as model weight bytes."""
    try:
        vm_after = subprocess.check_output(["vm_stat"], text=True, timeout=10)
        rows = instrument.parse_ps_tree(
            subprocess.check_output(["ps", "-axo", "pid=,ppid=,rss="], text=True, timeout=10)
        )
    except (OSError, subprocess.CalledProcessError):
        vm_after, rows = "", []
    root = h2h.pid_on_port(port)
    rss = instrument.tree_rss_gb(rows, root) if root else None
    delta = (
        instrument.vm_deltas_gb(
            instrument.parse_vm_stat(vm_before), instrument.parse_vm_stat(vm_after)
        )
        or {}
    )
    return {
        "tree_walked": root is not None and rss is not None,
        "tree_rss_gb": rss,
        "engine_weight_gb": None,
        "engine_weight_source": "",
        "engine_weight_reason": (
            "No verified engine-reported weight field is registered for this engine; "
            "process RSS is reported separately and is not a substitute."
        ),
        **delta,
    }


def _candidate_body(cell: dict[str, Any]) -> dict[str, Any]:
    """Build the same two-request preflight/noise probe for every cell."""
    return {
        "model": cell["workspace"],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Reply with exactly OK in visible text and invoke get_weather for Boston."
                ),
            }
        ],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
        "tools": instrument._TOOL_SPEC,
        "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        "think": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "portal_backend": cell["backend"],
    }


def _candidate_tokenizer(cfg: dict, cell: dict[str, Any]) -> Path | None:
    """Resolve the loaded checkpoint tokenizer from the benchmark registry."""
    entry = cfg["models"][cell["model"]]
    if cfg["engines"][cell["engine"]].get("requires") == "gguf":
        tokenizer = {"repo": entry["source_repo"], "file": "tokenizer.json"}
        try:
            return Path(h2h.cached_hf_file(tokenizer, cell["model"]))
        except SystemExit:
            return None
    directory = Path(h2h.model_root(cfg, cell["engine"])) / h2h.model_dir_for(
        cfg, cell["model"], cell["engine"], cell["mode"]
    )
    return instrument.resolve_tokenizer(cell["engine"], directory, None)


def _candidate_template(cfg: dict, cell: dict[str, Any]) -> dict[str, Any]:
    """Check templates only for cells that load the same registered checkpoint."""
    entry = cfg["models"][cell["model"]]
    is_gguf = cfg["engines"][cell["engine"]].get("requires") == "gguf"
    same = is_gguf or (
        cell["mode"] == "plain"
        and h2h.model_dir_for(cfg, cell["model"], cell["engine"], cell["mode"]) == entry.get("mlx")
    )
    if not same:
        return {"same_checkpoint": False}
    try:
        result = h2h.template_check(cfg, cell["engine"], cell["model"], cell["mode"])
    except (KeyError, OSError, SystemExit) as exc:
        return {"same_checkpoint": True, "match": False, "note": str(exc)}
    if result.get("ok") is True:
        return {"same_checkpoint": True, "match": True}
    return {
        "same_checkpoint": True,
        "match": False,
        "note": str(result.get("note") or "template comparison unavailable"),
    }


def collect_candidate_cell(cell: dict[str, Any], pipeline: str) -> dict[str, Any]:
    """Collect two routed requests, readbacks, tokens, and all-engine snapshots."""
    cfg = h2h.load_config()
    vm_before = subprocess.check_output(["vm_stat"], text=True, timeout=10)
    resident_before = _candidate_residency(cfg)
    served = instrument._served_ids(cell["base"])
    log_since = time.strftime("%Y-%m-%dT%H:%M:%S")
    body = _candidate_body(cell)
    url = f"{pipeline.rstrip('/')}/v1/chat/completions"
    rows = [instrument._one_chat(url, body, instrument._pipeline_headers()) for _ in range(2)]
    resident_after = _candidate_residency(cfg)
    log = instrument._pipeline_log_since(log_since)
    first_message = rows[0]["message"]
    preflight = instrument.grade_preflight(
        instrument._visible_reply(first_message),
        instrument.tool_from_message(first_message),
        next((item for item in served or [] if item == cell["expected_model"]), None),
    )
    tokenizer = _candidate_tokenizer(cfg, cell)
    excluded = {
        key: instrument._exclude(
            f"{cell['engine']} has no verified request-level readback source for this claim"
        )
        for key in instrument.REQUIRED_CLAIMS
    }
    sources = {
        "engine_models": f"POST /v1/chat/completions response.model ({OPENAI_CHAT_SOURCE})",
        "served_model_id": f"GET /v1/models ({OPENAI_MODELS_SOURCE})",
        "pipeline_route": "Pipeline response x-portal-route and docker logs for each request",
        "tokens": "Pipeline completion usage compared with the registered checkpoint tokenizer.json",
        "memory": "vm_stat wired delta and candidate process-tree RSS; engine weight source unavailable",
        "residency": "Ollama /api/ps; oMLX /v1/models/status; lsof listener and engine_h2h state per managed port",
    }
    evidence = {
        "engine": cell["engine"],
        "mode": cell["mode"],
        "claimed": {},
        "readback": {},
        "sources": {},
        "excluded_claims": excluded,
        "source_conflicts": [],
        "expected_model": cell["expected_model"],
        "expected_workspace": cell["workspace"],
        "expected_backend": cell["backend"],
        "routes": [{"header": row["header"], "engine_model": row["engine_model"]} for row in rows],
        "engine_models": [row["engine_model"] for row in rows],
        "pipeline_models": [model for _ws, _be, model in instrument.parse_pipeline_routes(log)],
        "memory": _candidate_memory(vm_before, cell["port"]),
        "residency": {"before": resident_before, "after": resident_after},
        "tokens": {
            "engine_completion": rows[0]["tokens"],
            "tokenizer_completion": instrument.count_tokens(rows[0]["text"], tokenizer)
            if tokenizer
            else None,
        },
        "noise": instrument._pair_noise([(row["tokens"], row["elapsed"]) for row in rows]),
        "template": _candidate_template(cfg, cell),
        "preflight_verdict": preflight["verdict"],
        "preflight": preflight,
        "swap_samples_mb": instrument._swap_pair(h2h.swap_now().get("used_mb")),
        "max_swap_growth_mb": cfg["guard"]["max_swap_growth_mb"],
        "max_start_swap_used_mb": cfg["guard"]["max_start_swap_used_mb"],
        "served_model_id": next(
            (item for item in served or [] if item == cell["expected_model"]), None
        ),
        "launch_argv": cell["argv"],
        "check_sources": {
            "route": "Pipeline x-portal-route + success log + engine response model",
            "memory": sources["memory"],
            "tokens": sources["tokens"],
            "noise": "two back-to-back Pipeline requests with the same body",
            "preflight": "think-off and get_weather call through the Pipeline",
            "residency": sources["residency"],
            "template": "registry model template vs source repository when same_checkpoint is true",
            "endpoint_sources": sources,
        },
    }
    return evidence


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a receipt atomically outside the checkout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def run_cell(cell: dict[str, Any], pipeline: str, build: str | None = None) -> dict[str, Any]:
    """Start one managed engine, run two Pipeline requests, and stop it."""
    root = data_root()
    _configure_results(root)
    cfg = h2h.load_config()
    build = build or current_build()
    receipt: dict[str, Any] = {
        "build": build,
        "cell": {key: cell[key] for key in ("engine", "mode", "seat", "workspace", "model")},
        "created_at": datetime.now(UTC).isoformat(),
        "valid": False,
        "failures": [],
        "evidence_sources": {
            "engine_request": OPENAI_CHAT_SOURCE,
            "engine_served_models": OPENAI_MODELS_SOURCE,
        },
    }
    started = False
    try:
        if cell.get("launch_error"):
            raise Stage3BlockedError(f"registry argv unavailable: {cell['launch_error']}")
        if h2h.pid_on_port(cell["port"]):
            raise Stage3BlockedError(f"candidate port {cell['port']} is already occupied")
        okay, reason = h2h.start_gate(cfg)
        if not okay:
            raise Stage3BlockedError(f"swap start gate: {reason}")
        with h2h.single_flight():
            started_info = h2h.start_managed(cfg, cell["engine"], cell["model"], cell["mode"])
            started = True
            evidence = collect_candidate_cell(cell, pipeline)
            evidence["launch_argv"] = started_info.get("argv") or cell["argv"]
            judged = instrument.judge_cell(evidence)
            receipt.update(
                {"evidence": evidence, "valid": judged["valid"], "failures": judged["failures"]}
            )
    except (
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        KeyError,
        Stage3BlockedError,
    ) as exc:
        receipt["failures"] = [f"candidate cell: {type(exc).__name__}: {exc}"]
    finally:
        if started:
            try:
                h2h.stop_managed(cfg, cell["engine"])
            except (OSError, subprocess.CalledProcessError, SystemExit) as exc:
                receipt["valid"] = False
                receipt.setdefault("failures", []).append(f"stop: {exc}")
    path = canary_receipt_path(root, build, cell)
    receipt["receipt"] = str(path)
    _write_json(path, receipt)
    return receipt


def run_canary(pipeline: str) -> tuple[list[dict[str, Any]], int]:
    """Run every registered matrix cell sequentially and print one table."""
    build = current_build()
    results = [run_cell(cell, pipeline, build) for cell in candidate_cells()]
    root = data_root()
    summary = root / "engine_eval" / "canaries" / build / "table.json"
    _write_json(summary, {"build": build, "cells": results})
    print("cell | valid | failures | evidence sources")
    for result in results:
        cell = result["cell"]
        sources = ", ".join(result.get("evidence_sources", {}).values())
        print(
            f"{cell['engine']} / {cell['mode']} / {cell['seat']} | "
            f"{str(result['valid']).lower()} | {'; '.join(result['failures'])} | {sources}"
        )
    return results, 0 if all(item["valid"] for item in results) else 2


def protocol_issues() -> dict[str, list[str]]:
    """Find approved workload plans that cannot map to the declared bench seats."""
    cfg = h2h.load_config()
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8")) or {}
    quality = (protocol.get("workloads") or [{}])[0]
    listed = set(quality.get("plans") or [])
    registered = {
        entry.get("quality_gate", {}).get("wfe_plan")
        for entry in cfg["models"].values()
        if entry.get("quality_gate")
    }
    issues: dict[str, list[str]] = {}
    unbound = sorted(path for path in listed if path not in registered)
    if unbound:
        issues["quality-seat"] = [f"plans lack a seat mapping: {unbound}"]
    baseline_issues = []
    for rel in sorted(listed & registered):
        plan = yaml.safe_load((REPO / rel).read_text(encoding="utf-8")) or {}
        for workspace, workload in (plan.get("workloads") or {}).items():
            arms = workload.get("arms") or {}
            incumbent = arms.get("incumbent")
            incumbent_model = incumbent.get("model") if isinstance(incumbent, dict) else incumbent
            candidate = next(iter(arms.get("challengers") or []), None)
            candidate_model = candidate.get("model") if isinstance(candidate, dict) else candidate
            if incumbent_model and not (isinstance(incumbent, dict) and incumbent.get("backend")):
                baseline_issues.append(
                    f"{rel} {workspace}: incumbent {incumbent_model!r} has no oMLX backend pin"
                )
            if candidate_model and incumbent_model and candidate_model != incumbent_model:
                baseline_issues.append(
                    f"{rel} {workspace}: incumbent and challenger are different model ids"
                )
    if baseline_issues:
        issues.setdefault("quality-seat", []).extend(baseline_issues)
    for index, workload in enumerate(protocol.get("workloads") or []):
        for seat in workload.get("seats") or []:
            if seat not in {
                entry["workspace"]
                for entry in (cfg.get("engine_eval") or {}).get("seats", {}).values()
            }:
                issues.setdefault(str(workload.get("id") or index), []).append(
                    f"protocol seat {seat} has no engine_eval seat mapping"
                )
    if "co-residence" in {str(item.get("id")) for item in protocol.get("workloads") or []}:
        issues.setdefault("co-residence", []).append(
            "engine_h2h.yaml launches one model per engine port; it has no same-engine multi-model resident operation"
        )
    return issues


def run_stage3(cell: dict[str, Any], workload: str, build: str | None = None) -> dict[str, Any]:
    """Gate protocol execution on a current valid canary and a resolvable mapping."""
    root = data_root()
    build = build or current_build()
    path = root / "engine_eval" / "stage3" / build / f"{_cell_id(cell)}--{workload}.json"
    try:
        canary = require_valid_canary(root, build, cell)
    except Stage3BlockedError as exc:
        result = {"valid": False, "status": "BLOCKED", "reason": str(exc)}
    else:
        issues = protocol_issues().get(workload) or []
        if issues:
            result = {
                "valid": False,
                "status": "BLOCKED",
                "reason": "; ".join(issues),
                "canary": canary["receipt"],
            }
        else:
            result = {
                "valid": False,
                "status": "BLOCKED",
                "reason": f"workload {workload!r} has no task-specific runner mapping",
                "canary": canary["receipt"],
            }
    result["receipt"] = str(path)
    _write_json(path, result)
    return result


def _select_cell(args: argparse.Namespace) -> dict[str, Any]:
    cell = next(
        (
            item
            for item in candidate_cells()
            if item["engine"] == args.engine
            and item["mode"] == args.mode
            and item["seat"] == args.seat
        ),
        None,
    )
    if cell is None:
        raise Stage3BlockedError(
            f"no approved candidate cell: {args.engine}/{args.mode}/{args.seat}"
        )
    return cell


def main(argv: list[str] | None = None) -> int:
    """Dispatch candidate cell, canary, or fail-closed Stage 3 work."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    canary = sub.add_parser("canary")
    canary.add_argument("--pipeline", default="http://127.0.0.1:9099")
    cell = sub.add_parser("cell")
    cell.add_argument("--engine", required=True)
    cell.add_argument("--mode", choices=("plain", "spec"), required=True)
    cell.add_argument("--seat", required=True)
    cell.add_argument("--pipeline", default="http://127.0.0.1:9099")
    stage3 = sub.add_parser("stage3")
    stage3.add_argument("--engine", required=True)
    stage3.add_argument("--mode", choices=("plain", "spec"), required=True)
    stage3.add_argument("--seat", required=True)
    stage3.add_argument("--workload", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "canary":
            _results, code = run_canary(args.pipeline)
            return code
        selected = _select_cell(args)
        if args.command == "cell":
            result = run_cell(selected, args.pipeline)
        else:
            result = run_stage3(selected, args.workload)
        print(json.dumps(result, indent=2))
        return 0 if result.get("valid") else 2
    except (OSError, subprocess.CalledProcessError, ValueError, Stage3BlockedError) as exc:
        print(json.dumps({"valid": False, "status": "BLOCKED", "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
