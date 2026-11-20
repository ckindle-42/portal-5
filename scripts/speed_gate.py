#!/usr/bin/env python3
"""oMLX speed gate: run the B1/B2/B3 baseline, then compare tags with setup proof.

Usage:
    uv run python scripts/speed_gate.py run <tag> [--out-dir DIR]
    uv run python scripts/speed_gate.py compare <tag> --against <tagA>[,<tagB>]

Cells: B1 direct oMLX per production-seat model, B2 workspaces through bench_tps,
B3 variant seats through speed_bench --engine pipeline. Rosters resolve from
config/backends.yaml and config/portal.yaml, never from a hardcoded list.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_ROOT = Path.home() / ".portal5" / "speed_gate"
DEFAULT_SIZES = (2000, 8000, 32000)
DEFAULT_RUNS = 3
DEFAULT_COOLDOWN_S = 10.0
RECLAIM_NEED_GIB = 64
RESET_SETTLE_S = 2.0
CELL_SETTLE_S = 1.0
REQUEST_TIMEOUT_S = 600.0
BENCH_TIMEOUT_S = 4 * 3600.0
KEYS = ("PIPELINE_API_KEY", "OMLX_API_KEY")
#: metric -> direction (+1 higher is better, -1 lower is better)
METRICS = {"decode_tps": 1, "prefill_tps": 1, "ttft_s": -1}
B2_METRICS = {"avg_tps": 1, "warm_ttft_s": -1}
PHASES = ("B1", "B2", "B3")
_READ_ERRORS = (OSError, ValueError, TimeoutError, urllib.error.URLError)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _failure(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def env_value(name: str, default: str = "") -> str:
    """Read one named value from the environment or the repo .env, never sourcing it."""
    value = os.environ.get(name)
    if value:
        return value
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'") or default
    return default


def credentials() -> dict[str, str]:
    """The only two .env values this gate reads."""
    return {name: env_value(name) for name in KEYS}


def _host_url(env_name: str, default: str) -> str:
    return (os.environ.get(env_name) or default).replace("host.docker.internal", "localhost")


class Http:
    """Minimal JSON client; the seam unit tests replace."""

    def json(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        merged = {"Content-Type": "application/json"} if data is not None else {}
        merged.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=merged, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else {}


def _bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"} if key else {}


def ollama_residents(payload: object) -> list[dict[str, Any]]:
    """Resident models named by an Ollama /api/ps body (recorded shape)."""
    rows = []
    for model in (payload or {}).get("models") or [] if isinstance(payload, dict) else []:
        if not isinstance(model, dict):
            continue
        name = model.get("name") or model.get("model")
        if name:
            size = model.get("size")
            rows.append(
                {"name": str(name), "size_gib": round(float(size) / 1024**3, 2) if size else None}
            )
    return rows


def omlx_residents(payload: object) -> list[dict[str, Any]]:
    """Models oMLX reports loaded in a /v1/models/status body (recorded shape)."""
    rows = []
    models = (payload or {}).get("models") or [] if isinstance(payload, dict) else []
    for model in models:
        if not isinstance(model, dict) or model.get("loaded") is False:
            continue
        name = model.get("id") or model.get("name")
        if name:
            size = model.get("estimated_size") or model.get("actual_size")
            rows.append(
                {"name": str(name), "size_gib": round(float(size) / 1024**3, 2) if size else None}
            )
    return rows


def capture(ctx: Ctx) -> dict[str, Any]:
    """Ollama and oMLX resident sets at this instant; errors are recorded, not raised."""
    snapshot: dict[str, Any] = {"sampled_at": _now(), "ollama": [], "omlx": [], "errors": {}}
    reads = (
        ("ollama", f"{ctx.ollama_url}/api/ps", {}, ollama_residents),
        (
            "omlx",
            f"{ctx.omlx_url}/v1/models/status",
            _bearer(ctx.omlx_key),
            omlx_residents,
        ),
    )
    for engine, url, headers, parse in reads:
        try:
            snapshot[engine] = parse(ctx.http.json(url, headers=headers, timeout=10.0))
        except _READ_ERRORS as exc:
            snapshot["errors"][engine] = _failure(exc)
    return snapshot


def _seats(portal: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for workspace_id, workspace in (portal.get("workspaces") or {}).items():
        if not isinstance(workspace, dict):
            continue
        yield workspace_id, workspace
        for variant, overrides in (workspace.get("variants") or {}).items():
            yield f"{workspace_id}::{variant}", {**workspace, **(overrides or {})}


def omlx_catalog(
    backends: dict[str, Any],
) -> tuple[dict[str, set[str]], dict[str, dict[str, str]]]:
    """Each oMLX backend group's model ids and alias map."""
    models: dict[str, set[str]] = {}
    aliases: dict[str, dict[str, str]] = {}
    for backend in backends.get("backends") or []:
        if backend.get("type") != "omlx":
            continue
        group = str(backend.get("group") or "")
        for model in backend.get("models") or []:
            model_id = str(model.get("id") if isinstance(model, dict) else model)
            models.setdefault(group, set()).add(model_id)
        aliases.setdefault(group, {}).update(backend.get("aliases") or {})
    return models, aliases


def _group_catalog(
    seat: str,
    routing: dict[str, Any],
    models: dict[str, set[str]],
    aliases: dict[str, dict[str, str]],
) -> tuple[set[str], dict[str, str]]:
    """The oMLX model ids and aliases a seat's routing groups can actually reach."""
    ids: set[str] = set()
    group_aliases: dict[str, str] = {}
    for group in routing.get(seat.partition("::")[0]) or []:
        ids |= models.get(str(group)) or set()
        group_aliases.update(aliases.get(str(group)) or {})
    return ids, group_aliases


def resolve_seats(portal: dict[str, Any], backends: dict[str, Any]) -> dict[str, str]:
    """Map every seat whose routed model_hint resolves onto an oMLX model."""
    models, aliases = omlx_catalog(backends)
    routing = backends.get("workspace_routing") or {}
    resolved: dict[str, str] = {}
    for seat, workspace in _seats(portal):
        hint = str(workspace.get("model_hint") or "").strip()
        if not hint:
            continue
        ids, group_aliases = _group_catalog(seat, routing, models, aliases)
        target = group_aliases.get(hint) or (hint if hint in ids else None)
        if target:
            resolved[seat] = target
    return resolved


def build_roster(backends: dict[str, Any], portal: dict[str, Any]) -> dict[str, Any]:
    """B1 models, B2 top-level workspaces, B3 variant seats — all derived from config."""
    seats = resolve_seats(portal, backends)
    routing = backends.get("workspace_routing") or {}
    skip = {str(item) for item in backends.get("pipeline_bench_skip") or []}
    workspaces = [ws for ws in routing if ws not in skip and ws in seats]
    workspaces.sort(key=lambda ws: (routing[ws][0] if routing[ws] else "", ws))
    return {
        "b1_models": sorted(set(seats.values())),
        "b2_workspaces": workspaces,
        "b3_seats": sorted(seat for seat in seats if "::" in seat),
        "seats": seats,
    }


def load_config(config_dir: Path = ROOT / "config") -> tuple[dict[str, Any], dict[str, Any]]:
    backends = yaml.safe_load((config_dir / "backends.yaml").read_text(encoding="utf-8")) or {}
    portal = yaml.safe_load((config_dir / "portal.yaml").read_text(encoding="utf-8")) or {}
    return backends, portal


def _names(snapshot: dict[str, Any], engine: str) -> list[str]:
    return [str(row["name"]) for row in snapshot.get(engine) or [] if row.get("name")]


def non_target(snapshot: dict[str, Any], targets: set[str]) -> list[str]:
    """Residents that are not this cell's target; every Ollama resident is one."""
    found = []
    for engine in ("ollama", "omlx"):
        for name in _names(snapshot, engine):
            if engine == "ollama" or name not in targets:
                found.append(f"{engine}/{name}")
    return found


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _reclaim(ctx: Ctx) -> dict[str, Any]:
    try:
        body = ctx.http.json(
            f"{ctx.pipeline_url}/admin/reclaim-idle",
            method="POST",
            payload={"need_gib": RECLAIM_NEED_GIB},
            headers=_bearer(ctx.pipeline_key),
            timeout=60.0,
        )
        return {"ok": True, "response": body}
    except _READ_ERRORS as exc:
        return {"ok": False, "error": _failure(exc)}


def _unload_ollama(ctx: Ctx, models: list[str]) -> list[dict[str, Any]]:
    results = []
    for model in models:
        try:
            ctx.http.json(
                f"{ctx.ollama_url}/api/generate",
                method="POST",
                payload={"model": model, "keep_alive": 0, "stream": False},
                timeout=30.0,
            )
            results.append({"model": model, "ok": True})
        except _READ_ERRORS as exc:
            results.append({"model": model, "ok": False, "error": _failure(exc)})
    return results


def _default_host_quiet() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "host_quiet.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-2000:],
    }


def precondition(ctx: Ctx) -> dict[str, Any]:
    """Unload Ollama residents, reclaim 64 GiB, then require host_quiet to pass."""
    record: dict[str, Any] = {"started_at": _now(), "ok": False, "problems": []}
    try:
        ps = ctx.http.json(f"{ctx.ollama_url}/api/ps", timeout=10.0)
    except _READ_ERRORS as exc:
        record["problems"].append(f"ollama /api/ps unavailable: {_failure(exc)}")
        record["finished_at"] = _now()
        return record
    residents = [str(row["name"]) for row in ollama_residents(ps)]
    record["ollama_before"] = residents
    record["unloads"] = _unload_ollama(ctx, residents)
    record["reclaim"] = _reclaim(ctx)
    if not record["reclaim"]["ok"]:
        record["problems"].append(f"reclaim-idle failed: {record['reclaim']['error']}")
    ctx.sleep(RESET_SETTLE_S)
    quiet = ctx.host_quiet()
    record["host_quiet"] = quiet
    if quiet.get("returncode") != 0:
        record["problems"].append("host is not quiet (host_quiet.py exited non-zero)")
    record["ok"] = not record["problems"]
    record["finished_at"] = _now()
    return record


def _setup_problems(
    before: dict[str, Any], after: dict[str, Any], targets: set[str]
) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    for label, snapshot in (("before", before), ("after", after)):
        for engine, detail in (snapshot.get("errors") or {}).items():
            problems.append(
                {"kind": "setup", "detail": f"{label}: {engine} unavailable ({detail})"}
            )
        for resident in non_target(snapshot, targets):
            problems.append({"kind": "setup", "detail": f"{resident} resident {label} cell"})
    return problems


def _instrument_failures(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return [str(item) for item in payload.get("failures") or []]


def _engine_problems(
    phase: str,
    model: str | None,
    payload: Any,
    after: dict[str, Any],
    returncode: int,
) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    failures = _instrument_failures(payload)
    if phase == "B1":
        if isinstance(payload, dict) and payload.get("engine") not in (None, "omlx"):
            problems.append({"kind": "engine", "detail": f"served engine {payload['engine']}"})
        if returncode and not isinstance(payload, dict):
            problems.append({"kind": "failed", "detail": "speed_bench produced no report"})
    elif phase == "B2":
        problems.extend(_b2_engine_problems(model, payload, after, returncode))
    else:
        for row in _payload_rows(payload):
            if row.get("engine_ok") is False:
                problems.append(
                    {
                        "kind": "engine",
                        "detail": f"size {row.get('size_tokens')} served "
                        f"{row.get('served_engine') or 'unknown'} / "
                        f"{row.get('served_model') or 'unknown'}",
                    }
                )
        problems.extend(
            {"kind": "engine", "detail": failure}
            for failure in failures
            if "WRONG ENGINE" in failure
        )
        if returncode and not isinstance(payload, dict):
            problems.append({"kind": "failed", "detail": "speed_bench produced no report"})
    if phase != "B2":
        problems.extend(
            {"kind": "failed", "detail": failure}
            for failure in failures
            if "WRONG ENGINE" not in failure
        )
        if returncode and payload is not None and not problems:
            problems.append({"kind": "failed", "detail": "speed_bench exited non-zero"})
    return problems


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _b2_engine_problems(
    model: str | None, payload: Any, after: dict[str, Any], returncode: int
) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    rows = payload.get("results") if isinstance(payload, dict) else None
    if returncode and not rows:
        problems.append({"kind": "failed", "detail": "bench_tps produced no report"})
        return problems
    for row in rows or []:
        if row.get("expected_model_match") is False:
            problems.append(
                {
                    "kind": "engine",
                    "detail": f"{row.get('model')} routed model {row.get('routed_model') or '?'} "
                    f"does not match {row.get('expected_model_detail') or '?'}",
                }
            )
    if "omlx" in (after.get("errors") or {}):
        return problems
    if model and model not in _names(after, "omlx"):
        problems.append(
            {
                "kind": "engine",
                "detail": f"served engine unproven: {model} is not resident on oMLX after the cell",
            }
        )
    if not rows or all((row.get("runs_success") or 0) == 0 for row in rows):
        problems.append({"kind": "failed", "detail": "no successful bench_tps run"})
    return problems


def _status(problems: list[dict[str, str]]) -> str:
    kinds = {problem["kind"] for problem in problems}
    if "setup" in kinds:
        return "invalid_setup"
    if "engine" in kinds:
        return "invalid_engine"
    return "failed" if "failed" in kinds else "ok"


def _speed(ctx: Ctx, engine: str, target: str, path: Path) -> int:
    runner: Callable[..., int] = ctx.speed or _default_speed
    return runner(ctx, engine, target, path)


def _default_speed(ctx: Ctx, engine: str, target: str, path: Path) -> int:
    from scripts import speed_bench

    direct = engine == "omlx"
    host = ctx.omlx_url if direct else ctx.pipeline_url
    return speed_bench.run_bench(
        engine,
        host,
        target,
        list(ctx.sizes),
        out=str(path),
        api_key=ctx.omlx_key if direct else ctx.pipeline_key,
        timeout=REQUEST_TIMEOUT_S,
    )


def _bench(ctx: Ctx, workspace: str, path: Path, log: Path) -> int:
    runner: Callable[..., int] = ctx.bench or _default_bench
    return runner(ctx, workspace, path, log)


def _default_bench(ctx: Ctx, workspace: str, path: Path, log: Path) -> int:
    command = [
        sys.executable,
        str(ROOT / "tests" / "benchmarks" / "bench_tps.py"),
        "--mode",
        "pipeline",
        "--workspace",
        workspace,
        "--runs",
        str(ctx.runs),
        "--order",
        "size",
        "--cooldown",
        str(ctx.cooldown),
        "--output",
        str(path),
    ]
    try:
        with log.open("w", encoding="utf-8") as handle:
            proc = subprocess.run(
                command,
                cwd=str(ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=BENCH_TIMEOUT_S,
            )
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124


def cell_name(phase: str, target: str) -> str:
    return f"{phase.lower()}_{target.replace('::', '__').replace('/', '-')}.json"


def _measure(ctx: Ctx, phase: str, target: str, path: Path) -> tuple[int, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    if phase == "B2":
        returncode = _bench(ctx, target, path, path.with_suffix(".log"))
    else:
        returncode = _speed(ctx, "omlx" if phase == "B1" else "pipeline", target, path)
    return returncode, _read_json(path)


def run_cell(ctx: Ctx, phase: str, target: str, model: str | None) -> dict[str, Any]:
    """Measure one cell and record the resident proof from just before and after it."""
    targets = {model} if model else set()
    before = capture(ctx)
    reset = None
    if non_target(before, targets):
        reset = _reclaim(ctx)
        ctx.sleep(RESET_SETTLE_S)
        before = capture(ctx)
    path = ctx.out_dir / cell_name(phase, target)
    started = _now()
    returncode, payload = _measure(ctx, phase, target, path)
    ctx.sleep(CELL_SETTLE_S)
    after = capture(ctx)
    problems = _setup_problems(before, after, targets)
    problems.extend(_engine_problems(phase, model, payload, after, returncode))
    return {
        "phase": phase,
        "target": target,
        "model": model,
        "started_at": started,
        "finished_at": _now(),
        "returncode": returncode,
        "status": _status(problems),
        "problems": problems,
        "setup": {"before": before, "after": after, "reset": reset},
        "instrument": payload,
    }


def _cell_summary(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "phase": cell["phase"],
        "target": cell["target"],
        "file": cell_name(cell["phase"], cell["target"]),
        "status": cell["status"],
        "problems": [problem["detail"] for problem in cell["problems"]],
    }


def _counts(cells: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"ok": 0, "invalid_setup": 0, "invalid_engine": 0, "failed": 0}
    for cell in cells:
        counts[cell["status"]] = counts.get(cell["status"], 0) + 1
    return counts


@dataclass
class Ctx:
    out_dir: Path
    pipeline_url: str
    omlx_url: str
    ollama_url: str
    pipeline_key: str
    omlx_key: str
    sizes: list[int] = field(default_factory=lambda: list(DEFAULT_SIZES))
    runs: int = DEFAULT_RUNS
    cooldown: float = DEFAULT_COOLDOWN_S
    http: Http = field(default_factory=Http)
    sleep: Callable[[float], None] = time.sleep
    speed: Callable[..., int] | None = None
    bench: Callable[..., int] | None = None
    host_quiet: Callable[[], dict[str, Any]] = _default_host_quiet


def context(out_dir: Path, args: argparse.Namespace) -> Ctx:
    keys = credentials()
    return Ctx(
        out_dir=out_dir,
        pipeline_url=_host_url("PIPELINE_URL", "http://localhost:9099").rstrip("/"),
        omlx_url=_host_url("OMLX_URL", "http://localhost:8085").rstrip("/"),
        ollama_url=_host_url("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        pipeline_key=keys["PIPELINE_API_KEY"],
        omlx_key=keys["OMLX_API_KEY"],
        sizes=args.sizes,
        runs=args.runs,
        cooldown=args.cooldown,
    )


def _phase_targets(roster: dict[str, Any]) -> list[tuple[str, list[str]]]:
    return [
        ("B1", roster["b1_models"]),
        ("B2", roster["b2_workspaces"]),
        ("B3", roster["b3_seats"]),
    ]


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = (args.out_dir or DEFAULT_OUT_ROOT) / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = context(out_dir, args)
    backends, portal = load_config()
    roster = build_roster(backends, portal)
    run: dict[str, Any] = {
        "schema": 1,
        "tag": args.tag,
        "started_at": _now(),
        "out_dir": str(out_dir),
        "sizes": ctx.sizes,
        "runs": ctx.runs,
        "roster": {key: roster[key] for key in ("b1_models", "b2_workspaces", "b3_seats")},
        "cells": [],
    }
    _write_json(out_dir / "run.json", run)
    run["precondition"] = precondition(ctx)
    _write_json(out_dir / "precondition.json", run["precondition"])
    _write_json(out_dir / "run.json", run)
    if not run["precondition"]["ok"]:
        run["stopped"] = "precondition"
        run["finished_at"] = _now()
        _write_json(out_dir / "run.json", run)
        print(f"ABORT {args.tag}: {'; '.join(run['precondition']['problems'])}", file=sys.stderr)
        return 3
    for phase, targets in _phase_targets(roster):
        for target in targets:
            model = target if phase == "B1" else roster["seats"].get(target)
            cell = run_cell(ctx, phase, target, model)
            _write_json(out_dir / cell_name(phase, target), cell)
            run["cells"].append(_cell_summary(cell))
            _write_json(out_dir / "run.json", run)
            print(f"{phase} {target} {cell['status']}", flush=True)
    run["finished_at"] = _now()
    run["counts"] = _counts(run["cells"])
    run["ok"] = run["counts"]["ok"] == len(run["cells"])
    _write_json(out_dir / "run.json", run)
    print(f"DONE {args.tag} {json.dumps(run['counts'])}")
    return 0 if run["ok"] else 1


def load_tag(out_dir: Path, tag: str) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for path in sorted((out_dir / tag).glob("b[123]_*.json")):
        cell = _read_json(path)
        if isinstance(cell, dict):
            cells[path.stem] = cell
    return cells


def _cell_rows(cell: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload = cell.get("instrument") or {}
    rows = payload.get("results") if isinstance(payload, dict) else None
    keyed: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("size_tokens", ""))
        if cell.get("phase") == "B2":
            key = str(row.get("workspace") or row.get("model") or "")
        if key:
            keyed[key] = row
    return keyed


def _warm_ttft(row: dict[str, Any]) -> float | None:
    runs = [
        run
        for run in row.get("runs") or []
        if isinstance(run, dict) and run.get("time_to_first_token_s") is not None
    ]
    warm = [run["time_to_first_token_s"] for run in runs[1:]]
    return round(sum(warm) / len(warm), 3) if warm else None


def metric_value(row: dict[str, Any], metric: str) -> float | None:
    value = _warm_ttft(row) if metric == "warm_ttft_s" else row.get(metric)
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _band(baselines: list[float], worse: float) -> float:
    if len(baselines) >= 2:
        return abs(baselines[0] - baselines[1])
    return 0.10 * abs(worse)


def _describe(stem: str, key: str, metric: str, pre: list[float], post: float, band: float) -> str:
    return f"{stem:58s} {key:>6} {metric:12s} pre={pre} post={post:.2f} band={band:.2f}"


def _compare_cell(
    stem: str,
    cell: dict[str, Any],
    baselines: list[dict[str, Any]],
    missing: list[str],
) -> tuple[list[str], list[str], int]:
    regressions: list[str] = []
    improved: list[str] = []
    within = 0
    phase = str(cell.get("phase"))
    rows = _cell_rows(cell)
    baseline_rows = [_cell_rows(baseline) for baseline in baselines]
    metrics = B2_METRICS if phase == "B2" else METRICS
    first_size = min((int(key) for key in rows if key.isdigit()), default=None)
    for key, row in rows.items():
        for metric, sign in metrics.items():
            post = metric_value(row, metric)
            pre = [
                value
                for value in (metric_value(rows_.get(key, {}), metric) for rows_ in baseline_rows)
                if value is not None
            ]
            if post is None:
                continue
            if not pre:
                missing.append(f"{stem} {key} {metric}")
                continue
            if metric == "ttft_s" and key.isdigit() and int(key) == first_size:
                continue
            worse = min(pre) if sign > 0 else max(pre)
            band = _band(pre, worse)
            if metric == "avg_tps":
                band = max(band, _cv_band(baselines, key, row, worse))
            delta = (post - worse) * sign
            tag = _describe(stem, key, metric, pre, post, band)
            if delta < -band:
                regressions.append(tag)
            elif delta > band:
                improved.append(tag)
            else:
                within += 1
    return regressions, improved, within


def _cv_band(baselines: list[dict[str, Any]], key: str, row: dict[str, Any], worse: float) -> float:
    cvs = [
        float(baseline_row["cv"])
        for baseline_row in (_cell_rows(baseline).get(key, {}) for baseline in baselines)
        if baseline_row.get("cv") is not None
    ]
    if row.get("cv") is not None:
        cvs.append(float(row["cv"]))
    return max(cvs) * abs(worse) if cvs else 0.0


def compare_tags(
    target: dict[str, dict[str, Any]],
    baselines: list[dict[str, dict[str, Any]]],
) -> tuple[list[str], int]:
    invalid: list[str] = []
    failed: list[str] = []
    regressions: list[str] = []
    improved: list[str] = []
    missing: list[str] = []
    dropped: list[str] = []
    within = 0
    for stem, cell in target.items():
        status = cell.get("status")
        if status == "failed":
            failed.append(f"{stem}: {_problems(cell)}")
            continue
        if status != "ok":
            invalid.append(f"target {stem}: {status} — {_problems(cell)}")
            continue
        usable = []
        seen = False
        for baseline in baselines:
            other = baseline.get(stem)
            if other is None:
                continue
            seen = True
            if other.get("status") != "ok":
                invalid.append(f"baseline {stem}: {other.get('status')} — {_problems(other)}")
                continue
            usable.append(other)
        if not usable:
            if not seen:
                missing.append(stem)
            continue
        r, i, w = _compare_cell(stem, cell, usable, missing)
        regressions.extend(r)
        improved.extend(i)
        within += w
    known = {stem for baseline in baselines for stem in baseline}
    dropped = sorted(known - set(target))
    lines = [
        f"INVALID ({len(invalid)}):",
        *(f"  {line}" for line in invalid),
        f"FAILED ({len(failed)}):",
        *(f"  {line}" for line in failed),
        f"REGRESSIONS ({len(regressions)}):",
        *(f"  {line}" for line in regressions),
        f"IMPROVED ({len(improved)}):",
        *(f"  {line}" for line in improved),
        f"WITHIN BAND: {within}",
        f"NO BASELINE ({len(missing)}):",
        *(f"  {line}" for line in missing[:50]),
        f"MISSING FROM TARGET ({len(dropped)}):",
        *(f"  {line}" for line in dropped),
    ]
    return lines, 1 if (invalid or failed or regressions) else 0


def _problems(cell: dict[str, Any]) -> str:
    details = [problem.get("detail", "") for problem in cell.get("problems") or []]
    return "; ".join(detail for detail in details if detail) or "no detail"


def cmd_compare(args: argparse.Namespace) -> int:
    out_dir = args.out_dir or DEFAULT_OUT_ROOT
    target = load_tag(out_dir, args.tag)
    if not target:
        print(f"no cells under {out_dir / args.tag}", file=sys.stderr)
        return 2
    baselines = []
    for tag in args.against:
        cells = load_tag(out_dir, tag)
        if not cells:
            print(f"no cells under {out_dir / tag}", file=sys.stderr)
            return 2
        baselines.append(cells)
    lines, code = compare_tags(target, baselines)
    print("\n".join(lines))
    return code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="oMLX speed gate (B1/B2/B3) with setup proof.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="measure a tag")
    run.add_argument("tag")
    run.add_argument("--out-dir", type=Path, default=None, help=f"default {DEFAULT_OUT_ROOT}")
    run.add_argument("--sizes", type=_sizes, default=list(DEFAULT_SIZES))
    run.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    run.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN_S)
    run.set_defaults(func=cmd_run)
    compare = sub.add_parser("compare", help="compare a tag against baseline tags")
    compare.add_argument("tag")
    compare.add_argument("--against", type=_tags, required=True)
    compare.add_argument("--out-dir", type=Path, default=None, help=f"default {DEFAULT_OUT_ROOT}")
    compare.set_defaults(func=cmd_compare)
    return parser


def _sizes(spec: str) -> list[int]:
    try:
        sizes = [int(part) for part in spec.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"sizes must be integers, got {spec!r}") from exc
    if not sizes or any(size <= 0 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must be positive integers")
    return sizes


def _tags(spec: str) -> list[str]:
    tags = [part.strip() for part in spec.split(",") if part.strip()]
    if not tags:
        raise argparse.ArgumentTypeError("--against needs at least one tag")
    return tags


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
