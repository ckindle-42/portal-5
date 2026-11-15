"""Production-fit gate for one engine cell: co-residence, lifecycle, operations.

Speed and quality do not answer "can this engine be used in our setup?". This module
answers that with three evidence blocks per (engine, mode, seat) cell, recorded under
``$PORTAL_DATA_ROOT/engine_eval/prodfit/<build>/``.
"""

from __future__ import annotations

import json
import platform
import plistlib
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from tests.benchmarks import bench_engine_h2h as h2h
from tests.benchmarks import engine_eval_instrument as instrument

REPO = Path(__file__).resolve().parents[2]
BENCH_ENGINES = REPO / "config" / "bench_engines.yaml"
REQUEST_TIMEOUT_S = 600.0
STOP_TIMEOUT_S = 30.0
HEALTH_TIMEOUT_S = 15.0
PIPELINE_HEALTH_TIMEOUT_S = 120.0
PROBE = "Reply exactly OK."
_MEM_FREE = re.compile(r"memory free percentage\s*:\s*([0-9.]+)%", re.IGNORECASE)
_OOM = re.compile(r"out of memory|OutOfMemory|MemoryError|jetsam", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{[a-z_][a-z_0-9]*\}")


class ProdfitBlockedError(ValueError):
    """The cell cannot be judged production-fit on this host."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _status(valid: bool) -> str:
    return "PASS" if valid else "FAIL"


def _item(
    name: str,
    pass_rule: str,
    checks: dict[str, dict[str, Any]],
    evidence: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    failed = [key for key, check in checks.items() if check.get("pass") is not True]
    valid = not failed
    return {
        "item": name,
        "status": _status(valid),
        "valid": valid,
        "pass_rule": pass_rule,
        "reason": reason or (f"failed: {', '.join(failed)}" if failed else None),
        "checks": checks,
        "evidence": evidence,
    }


def _check(passed: bool, **evidence: Any) -> dict[str, Any]:
    return {"pass": bool(passed), **evidence}


def _command(argv: list[str], timeout: float = 15) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    return result.stdout.strip() or result.stderr.strip()


def _http(
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = HEALTH_TIMEOUT_S,
) -> dict[str, Any]:
    """One JSON call, keeping the status and body a failure would otherwise hide."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local
            raw = response.read()
            return {
                "status": int(response.status),
                "json": json.loads(raw) if raw else {},
                "headers": dict(response.headers),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return {"status": exc.code, "json": _maybe_json(body), "headers": {}, "error": body[:500]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "json": {}, "headers": {}, "error": f"{type(exc).__name__}: {exc}"}


def _maybe_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _detail(sent: dict[str, Any]) -> str:
    body = sent.get("json") or {}
    detail = body.get("detail") if isinstance(body, dict) else None
    return str(detail or sent.get("error") or "")[:500]


def _text(sent: dict[str, Any]) -> str:
    choices = (sent.get("json") or {}).get("choices") or [{}]
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    return str((message or {}).get("content") or "")


def prodfit_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """The ``prodfit:`` registry block: production seats, the stack, and their routes."""
    config = cfg if cfg is not None else h2h.load_config()
    block = config.get("prodfit") or {}
    if not block.get("production_seats"):
        raise ProdfitBlockedError("engine_h2h.yaml has no prodfit.production_seats block")
    return block


def receipt_path(root: Path, build: str, cell: dict[str, Any], cell_id: str) -> Path:
    return root / "engine_eval" / "prodfit" / build / f"{cell_id}.json"


def _context(cell: dict[str, Any], pipeline: str, build: str, root: Path) -> dict[str, Any]:
    cfg = h2h.load_config()
    block = prodfit_config(cfg)
    seats = block["production_seats"]
    others = [{"seat": seat, **target} for seat, target in seats.items()]
    others = [target for target in others if target["seat"] != cell["seat"]]
    cell_id = "--".join(str(cell[key]) for key in ("engine", "mode", "seat"))
    receipt = receipt_path(root, build, cell, cell_id)
    return {
        "cell": cell,
        "cell_id": cell_id,
        "cfg": cfg,
        "block": block,
        "pipeline": pipeline.rstrip("/"),
        "build": build,
        "others": others,
        "seat_is_production": cell["seat"] in seats,
        "dir": receipt.parent,
        "receipt": receipt,
    }


def _pipeline_sees_backend(
    pipeline: str, backend: str, timeout_s: float = PIPELINE_HEALTH_TIMEOUT_S
) -> dict[str, Any]:
    """Wait until the Pipeline's own backend list calls this eval backend healthy."""
    started = time.monotonic()
    last: dict[str, Any] = {}
    while True:
        sent = _http(f"{pipeline}/v1/backends", headers=instrument._pipeline_headers())
        last = sent.get("json") or {}
        rows = last.get("data") if isinstance(last.get("data"), list) else []
        row = next(
            (item for item in rows if isinstance(item, dict) and item.get("id") == backend), None
        )
        if isinstance(row, dict) and row.get("healthy") is True:
            return {"ready": True, "backend": row, "waited_s": round(time.monotonic() - started, 2)}
        if time.monotonic() - started >= timeout_s:
            return {
                "ready": False,
                "waited_s": round(time.monotonic() - started, 2),
                "last": last,
                "error": sent.get("error"),
            }
        time.sleep(2)


def _start_candidate(ctx: dict[str, Any]) -> dict[str, Any]:
    """Start the cell's managed engine under the runner's own start gate."""
    cell = ctx["cell"]
    if cell.get("engine_kind") != "managed":
        raise ProdfitBlockedError(f"{cell['engine']} is external; prod-fit runs managed candidates")
    port = int(cell["port"])
    if h2h.pid_on_port(port):
        raise ProdfitBlockedError(f"candidate port {port} is already occupied")
    okay, reason = h2h.start_gate(ctx["cfg"])
    if not okay:
        raise ProdfitBlockedError(f"swap start gate: {reason}")
    log_dir = ctx["dir"] / "logs" / ctx["cell_id"]
    started = time.monotonic()
    host_before = _host_memory()
    info = h2h.start_managed(
        ctx["cfg"],
        cell["engine"],
        cell["model"],
        cell["mode"],
        seat=cell.get("seat"),
        log_paths=(log_dir / "engine.stdout.log", log_dir / "engine.stderr.log"),
    )
    ctx["pipeline_backend"] = _pipeline_sees_backend(ctx["pipeline"], str(cell["backend"]))
    host_after = _host_memory()
    return {
        "pid": info["pid"],
        "argv": info["argv"],
        "cwd": info.get("cwd", cell.get("cwd")),
        "ready_s": info.get("ready_s"),
        "start_wall_s": round(time.monotonic() - started, 2),
        "engine_version": info.get("engine_version"),
        "logs": {"stdout": info["stdout_log"], "stderr": info["stderr_log"]},
        "swap_start_gate": {"ok": okay, "reason": reason},
        "pipeline_backend": ctx["pipeline_backend"],
        "host_before_load": host_before,
        "host_after_load": host_after,
        "vm_stat_delta": instrument.vm_deltas_gb(host_before["vm_stat"], host_after["vm_stat"]),
    }


def _stop_candidate(ctx: dict[str, Any]) -> dict[str, Any]:
    """The only Pipeline-side unload a managed process has: stop it and free the port."""
    cell = ctx["cell"]
    started = time.monotonic()
    h2h.stop_managed(ctx["cfg"], cell["engine"])
    deadline = time.monotonic() + STOP_TIMEOUT_S
    while h2h.pid_on_port(int(cell["port"])) and time.monotonic() < deadline:
        time.sleep(0.25)
    listener = h2h.pid_on_port(int(cell["port"]))
    return {
        "stop_s": round(time.monotonic() - started, 2),
        "port": int(cell["port"]),
        "port_free": not listener,
        "listener": listener,
    }


def _candidate_log_text(ctx: dict[str, Any]) -> str:
    log_dir = ctx["dir"] / "logs" / ctx["cell_id"]
    parts = []
    for name in ("engine.stdout.log", "engine.stderr.log"):
        path = log_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace")[-200_000:])
    return "\n".join(parts)


def _host_memory() -> dict[str, Any]:
    """vm_stat pages, swap, and the two macOS pressure readings."""
    vm = instrument.parse_vm_stat(_command(["vm_stat"]))
    page = vm.get("page_bytes")
    scale = page / (1024**3) if page else None
    free_text = _command(["memory_pressure", "-Q"])
    free = _MEM_FREE.search(free_text)
    level = _command(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
    return {
        "vm_wired_gb": round(vm["wired_pages"] * scale, 2)
        if scale and "wired_pages" in vm
        else None,
        "vm_free_gb": round(vm["free_pages"] * scale, 2) if scale and "free_pages" in vm else None,
        "vm_stat": vm,
        "swap_used_mb": h2h.swap_now().get("used_mb"),
        "memory_free_pct": float(free.group(1)) if free else None,
        "pressure_level": int(level) if level.isdigit() else None,
        "at": _now(),
    }


def _omlx_state(cfg: dict[str, Any]) -> dict[str, Any]:
    base = h2h.base_url(cfg, "omlx")
    sent = _http(f"{base}/v1/models/status", headers=h2h._headers(base))
    payload = sent.get("json") or {}
    rows = [row for row in payload.get("models") or [] if isinstance(row, dict)]
    return {
        "status": sent["status"],
        "error": sent.get("error"),
        "loaded": {str(row.get("id")): bool(row.get("loaded")) for row in rows if row.get("id")},
        "models": rows,
        "final_ceiling_gb": _gib(payload.get("final_ceiling")),
        "current_model_memory_gb": _gib(payload.get("current_model_memory")),
    }


def _gib(value: Any) -> float | None:
    try:
        return round(float(value) / 1024**3, 2)
    except (TypeError, ValueError):
        return None


def _ollama_loaded(cfg: dict[str, Any]) -> dict[str, Any]:
    base = h2h.base_url(cfg, "ollama")
    sent = _http(f"{base}/api/ps", headers=h2h._headers(base))
    rows = [row for row in (sent.get("json") or {}).get("models") or [] if isinstance(row, dict)]
    return {
        "status": sent["status"],
        "loaded": [str(row.get("name")) for row in rows if row.get("name")],
        "error": sent.get("error"),
    }


def _get_text(
    url: str, headers: dict[str, str] | None = None, timeout: float = 30
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local
            return {
                "status": int(response.status),
                "text": response.read().decode("utf-8", "replace"),
            }
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "text": exc.read().decode("utf-8", "replace")[:500]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "text": f"{type(exc).__name__}: {exc}"}


def _guard_metrics(pipeline: str) -> dict[str, Any]:
    """The load guard's own counters at this moment: the production memory verdict."""
    sent = _get_text(f"{pipeline}/metrics", instrument._pipeline_headers())
    series = {}
    for line in str(sent.get("text") or "").splitlines():
        if line.startswith("#") or not line.startswith("portal5_load_guard_"):
            continue
        name, _, value = line.rpartition(" ")
        try:
            series[name.strip()] = float(value)
        except ValueError:
            continue
    return {"status": sent["status"], "series": series}


def _guard_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
    """Counters that moved during the mixed load; an unload here is a displacement signal."""
    keys = {
        key: round(after["series"].get(key, 0.0) - before["series"].get(key, 0.0), 3)
        for key in set(before["series"]) | set(after["series"])
        if "unloads_total" in key or "refusals_total" in key or "admissions_total" in key
    }
    return {key: value for key, value in keys.items() if value}


def _load_plan(ctx: dict[str, Any], seats: list[dict[str, Any]]) -> dict[str, Any]:
    """What production's own memory admission says about the resident seat set."""
    models = [{"engine": "omlx", "model": target["model"]} for target in seats]
    sent = _http(
        f"{ctx['pipeline']}/admin/load-plan",
        {"models": models},
        instrument._pipeline_headers(),
        60,
    )
    return {
        "status": sent["status"],
        "error": sent.get("error"),
        "requested": models,
        "plan": sent.get("json") or {},
        "candidate_covered": False,
        "candidate_note": (
            "the load guard admits ollama and omlx only; a candidate engine on its own port "
            "is charged by the host, not by the guard"
        ),
    }


def _budget_source(plan: dict[str, Any], omlx: dict[str, Any]) -> dict[str, Any]:
    """Name the budget the guard's headroom came from: oMLX's live ceiling or a fixed cap."""
    headroom = (plan.get("plan") or {}).get("headroom_gib")
    ceiling = omlx.get("final_ceiling_gb")
    current = omlx.get("current_model_memory_gb")
    implied = None
    if isinstance(headroom, (int, float)) and ceiling is not None and current is not None:
        implied = round(float(headroom) + float(current), 2)
    live = implied is not None and abs(implied - float(ceiling)) <= 0.5
    return {
        "headroom_gib": headroom,
        "omlx_final_ceiling_gb": ceiling,
        "omlx_current_model_memory_gb": current,
        "headroom_plus_residents_gib": implied,
        "budget_source": (
            "omlx final_ceiling (LOAD_GUARD_CEILING_GB unset)"
            if live
            else "fixed LOAD_GUARD_CEILING_GB or unreadable ceiling"
        ),
        "budget_rule": "load_guard.plan: headroom = oMLX final_ceiling - residents, plus idle "
        "Ollama residents, minus LOAD_GUARD_MARGIN_GB; LOAD_GUARD_CEILING_GB replaces the ceiling",
    }


def _stack(ctx: dict[str, Any]) -> dict[str, Any]:
    """Every service the brief says must stay up while the candidate runs."""
    entries = ctx["block"].get("stack") or []
    rows = []
    for entry in entries:
        url = entry.get("url") or f"{ctx['pipeline']}{entry.get('path', '/v1/models')}"
        headers = instrument._pipeline_headers() if url.startswith(ctx["pipeline"]) else {}
        sent = _http(url, headers=headers)
        rows.append(
            {
                "name": entry.get("name"),
                "url": url,
                "status": sent["status"],
                "ok": sent["status"] == 200,
                "error": sent.get("error"),
            }
        )
    down = [row["name"] for row in rows if not row["ok"]]
    return {"valid": not down and bool(rows), "down": down, "services": rows}


def _seat_request(workspace: str, backend: str | None, pipeline: str, phase: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": workspace,
        "messages": [{"role": "user", "content": PROBE}],
        "temperature": 0,
        "max_tokens": 128,
        "stream": False,
    }
    if backend:
        body["portal_backend"] = backend
    started = time.monotonic()
    sent = _http(
        f"{pipeline}/v1/chat/completions", body, instrument._pipeline_headers(), REQUEST_TIMEOUT_S
    )
    header = sent["headers"].get("x-portal-route") or sent["headers"].get("X-Portal-Route") or ""
    return {
        "phase": phase,
        "workspace": workspace,
        "backend": backend,
        "status": sent["status"],
        "elapsed_s": round(time.monotonic() - started, 3),
        "route": header,
        "engine_model": (sent.get("json") or {}).get("model"),
        "answered": bool((sent.get("json") or {}).get("choices")),
        "text": _text(sent),
        "reasoning_chars": _reasoning_chars(sent),
        "error": _detail(sent),
    }


def _pinned_route_ok(row: dict[str, Any], cell: dict[str, Any]) -> bool:
    """Proof the request was served by the pinned backend, not a fallback.

    Model identity is the canary's and Stage 0's job; here the question is only which
    engine answered.
    """
    match = instrument._ROUTE_RE.match(str(row.get("route") or ""))
    if not match:
        return False
    workspace, backend, _model = match.groups()
    return workspace == cell["workspace"] and backend == cell["backend"]


def _reasoning_chars(sent: dict[str, Any]) -> int:
    choices = (sent.get("json") or {}).get("choices") or [{}]
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    message = message if isinstance(message, dict) else {}
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    return len(str(reasoning))


def _row_ok(row: dict[str, Any]) -> bool:
    """Served means the Pipeline returned a completion; an empty answer is a
    quality/settings finding for the canary, not a co-residence failure."""
    return row["status"] == 200 and bool(row.get("answered"))


def _candidate_row(ctx: dict[str, Any], phase: str) -> dict[str, Any]:
    cell = ctx["cell"]
    row = _seat_request(cell["workspace"], cell["backend"], ctx["pipeline"], phase)
    row["pinned_route_ok"] = _pinned_route_ok(row, cell)
    row["ok"] = _row_ok(row) and row["pinned_route_ok"]
    return row


def _concurrent_candidate_rows(ctx: dict[str, Any], workers: int) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_candidate_row, ctx, f"candidate-concurrent-{index + 1}")
            for index in range(workers)
        ]
        return [future.result() for future in futures]


def _warm(seats: list[dict[str, Any]], pipeline: str) -> list[dict[str, Any]]:
    rows = []
    for target in seats:
        row = _seat_request(target["workspace"], target["backend"], pipeline, "production-warm")
        row["seat"] = target["seat"]
        row["ok"] = _row_ok(row)
        rows.append(row)
    return rows


def _missing_seats(seats: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    state = _omlx_state(cfg)
    missing = [t["model"] for t in seats if state["loaded"].get(t["model"]) is not True]
    return {"state": state, "missing": missing}


def _warm_production(ctx: dict[str, Any]) -> dict[str, Any]:
    """Production seats resident before the candidate loads: the eviction baseline."""
    stack = _stack(ctx)
    if not stack["valid"]:
        return {"valid": False, "stack": stack, "warm": [], "loaded": {"missing": []}}
    warm = _warm(ctx["others"], ctx["pipeline"])
    loaded = _missing_seats(ctx["others"], ctx["cfg"])
    return {"valid": True, "stack": stack, "warm": warm, "loaded": loaded}


def _snapshot(ctx: dict[str, Any], seats: list[dict[str, Any]]) -> dict[str, Any]:
    omlx = _omlx_state(ctx["cfg"])
    plan = _load_plan(ctx, seats)
    return {
        "at": _now(),
        "host": _host_memory(),
        "omlx": omlx,
        "ollama": _ollama_loaded(ctx["cfg"]),
        "load_plan": plan,
        "budget": _budget_source(plan, omlx),
        "guard_metrics": _guard_metrics(ctx["pipeline"]),
        "candidate_pid": h2h.pid_on_port(int(ctx["cell"]["port"])),
    }


def _swap_gate(
    ctx: dict[str, Any], before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    guard = ctx["cfg"]["guard"]
    samples = [
        {"used_mb": before["host"]["swap_used_mb"]},
        {"used_mb": after["host"]["swap_used_mb"]},
    ]
    verdict = h2h.guard_verdict(
        [s for s in samples if s["used_mb"] is not None],
        float(guard["max_swap_growth_mb"]),
        float(guard["max_start_swap_used_mb"]),
    )
    return {
        "valid": verdict["valid"],
        "reasons": verdict["reasons"],
        "swap_before_mb": samples[0]["used_mb"],
        "swap_after_mb": samples[1]["used_mb"],
        "swap_growth_mb": verdict["swap_growth_mb"],
        "max_swap_growth_mb": guard["max_swap_growth_mb"],
        "max_swap_used_mb": guard["max_start_swap_used_mb"],
        "gate": "engine_h2h.yaml guard: max_swap_growth_mb and max_start_swap_used_mb",
    }


def _co_residence_checks(
    ctx: dict[str, Any], mixed: dict[str, Any], evicted: dict[str, Any], gate: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    production = mixed["production"]
    candidate = mixed["candidate"]
    return {
        "stack_up": _check(mixed["stack"]["valid"], down=mixed["stack"]["down"]),
        "pipeline_sees_candidate": _check(
            ctx.get("pipeline_backend", {}).get("ready") is True,
            health=ctx.get("pipeline_backend"),
        ),
        "other_seats_loaded_before": _check(
            not mixed["loaded_before"]["missing"], missing=mixed["loaded_before"]["missing"]
        ),
        "one_request_per_seat": _check(
            all(row["ok"] for row in production),
            rows=[
                {"seat": row["seat"], "status": row["status"], "elapsed_s": row["elapsed_s"]}
                for row in production
            ],
        ),
        "candidate_served_pinned_route": _check(
            all(row["ok"] for row in candidate),
            rows=[
                {"status": row["status"], "route": row["route"], "elapsed_s": row["elapsed_s"]}
                for row in candidate
            ],
        ),
        "no_production_eviction": _check(not evicted["missing"], missing=evicted["missing"]),
        "swap_gate": _check(gate["valid"], reasons=gate["reasons"]),
        "candidate_still_alive": _check(
            mixed["after"]["candidate_pid"] is not None,
            pid=mixed["after"]["candidate_pid"],
        ),
    }


def _co_residence(ctx: dict[str, Any]) -> dict[str, Any]:
    """Candidate on its seat beside the other production seats and the running stack."""
    seats = ctx["others"]
    pre = ctx.get("pre_candidate") or {}
    stack = pre.get("stack") or {"valid": False, "down": ["pre-candidate warm did not run"]}
    if pre.get("valid") is not True:
        return _item(
            "co-residence",
            "candidate runs on its seat beside the other two production seats and the stack",
            {"production_seats_warm": _check(False, pre_candidate=pre)},
            {"pre_candidate": pre},
            reason="the other production seats could not be warmed before the candidate loaded",
        )
    if not stack["valid"]:
        return _item(
            "co-residence",
            "candidate runs on its seat beside the other two production seats and the stack",
            {"stack_up": _check(False, down=stack["down"])},
            {"stack": stack},
            reason=f"production stack is not up: {stack['down']}",
        )
    warm = pre.get("warm") or []
    loaded_before = pre.get("loaded") or {"missing": []}
    before = _snapshot(ctx, seats)
    production = []
    for target in seats:
        row = _seat_request(target["workspace"], target["backend"], ctx["pipeline"], "mixed-load")
        row["seat"] = target["seat"]
        row["ok"] = _row_ok(row)
        production.append(row)
    candidate = [_candidate_row(ctx, "candidate-single")]
    candidate += _concurrent_candidate_rows(ctx, int(ctx["block"].get("concurrency") or 2))
    after = _snapshot(ctx, seats)
    evicted = _missing_seats(seats, ctx["cfg"])
    gate = _swap_gate(ctx, before, after)
    mixed = {
        "stack": stack,
        "warm": warm,
        "loaded_before": loaded_before,
        "production": production,
        "candidate": candidate,
        "before": before,
        "after": after,
    }
    checks = _co_residence_checks(ctx, mixed, evicted, gate)
    guard_delta = _guard_delta(before["guard_metrics"], after["guard_metrics"])
    oom = sorted({match.group(0).lower() for match in _OOM.finditer(_candidate_log_text(ctx))})
    warnings = _co_residence_warnings(mixed, gate, oom, guard_delta)
    item = _item(
        "co-residence",
        "candidate runs on its seat beside the other two production seats and the stack; "
        "no production seat is evicted and swap stays inside the runner's guard",
        checks,
        {
            "production_seats": [{"seat": t["seat"], "model": t["model"]} for t in seats],
            "warm_requests": warm,
            "production_requests": production,
            "candidate_requests": candidate,
            "before": before,
            "after": after,
            "evicted": evicted,
            "swap": gate,
            "load_guard_delta": guard_delta,
            "oom_log_hits": oom,
            "vm_stat_delta": instrument.vm_deltas_gb(
                before["host"]["vm_stat"], after["host"]["vm_stat"]
            ),
        },
    )
    item["warnings"] = warnings
    return item


def _co_residence_warnings(
    mixed: dict[str, Any], gate: dict[str, Any], oom: list[str], guard_delta: dict[str, float]
) -> list[str]:
    warnings = []
    after_pressure = mixed["after"]["host"]["pressure_level"]
    if after_pressure is not None and after_pressure >= 4:
        warnings.append("kernel memory pressure reached critical (level 4) during the mixed load")
    if oom:
        warnings.append(f"candidate log names memory exhaustion: {oom}")
    if any("unloads_total" in key for key in guard_delta):
        warnings.append("the load guard unloaded a model during the mixed load; check eviction")
    if any("refusals_total" in key for key in guard_delta):
        warnings.append("the load guard refused a load during the mixed load")
    slow = [row["seat"] for row in mixed["production"] if row["elapsed_s"] > 30]
    if slow:
        warnings.append(f"production seat request was slow (cold reload suspected): {slow}")
    return warnings


def _seat_target(seat: str, block: dict[str, Any]) -> dict[str, Any] | None:
    for name, target in (block.get("production_seats") or {}).items():
        if name == seat:
            return {"seat": name, **target}
    return None


def _down_probes(ctx: dict[str, Any]) -> dict[str, Any]:
    """What answers while the candidate is stopped: production route, Ollama, exclusive."""
    cell = ctx["cell"]
    rows: dict[str, Any] = {}
    target = _seat_target(str(cell["seat"]), ctx["block"])
    if target:
        route = target.get("production_route") or {}
        rows["production_route"] = _seat_request(
            str(route.get("workspace")),
            str(route.get("backend")),
            ctx["pipeline"],
            "down-production",
        )
        rows["ollama_fallback"] = _fallback_row(target, route, rows["production_route"], ctx)
    started = time.monotonic()
    exclusive = _seat_request(cell["workspace"], cell["backend"], ctx["pipeline"], "down-exclusive")
    exclusive["wall_s"] = round(time.monotonic() - started, 2)
    rows["exclusive_workspace"] = exclusive
    for row in rows.values():
        row["ok"] = _row_ok(row)
    rows["exclusive_workspace"]["definite"] = rows["exclusive_workspace"]["status"] is not None
    return rows


def _fallback_row(
    target: dict[str, Any],
    route: dict[str, Any],
    production: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    fallback = str(target.get("fallback_backend") or "")
    if not fallback or fallback == str(route.get("backend")):
        return {
            **production,
            "phase": "down-ollama-fallback",
            "backend": fallback or route.get("backend"),
            "note": "this seat's production route already is its Ollama fallback",
        }
    return _seat_request(
        str(route.get("workspace")), fallback, ctx["pipeline"], "down-ollama-fallback"
    )


def _down_checks(ctx: dict[str, Any], down: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A seat with no production route has nothing to fall back to; record it, do not fail."""
    if not ctx["seat_is_production"]:
        note = f"{ctx['cell']['seat']} is not a production seat; no production route to check"
        return {
            "production_route_answers_while_down": _check(True, not_applicable=note),
            "ollama_fallback_answers_while_down": _check(True, not_applicable=note),
        }
    return {
        "production_route_answers_while_down": _check(
            bool(down.get("production_route", {}).get("ok")),
            row=down.get("production_route"),
        ),
        "ollama_fallback_answers_while_down": _check(
            bool(down.get("ollama_fallback", {}).get("ok")),
            row=down.get("ollama_fallback"),
        ),
    }


def _lifecycle(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stop/reload under Pipeline control, and what still answers while it is down."""
    stop = _stop_candidate(ctx)
    down = _down_probes(ctx) if stop["port_free"] else {}
    restart = _start_candidate(ctx) if stop["port_free"] else {"ready_s": None}
    first = _candidate_row(ctx, "reload-first-request") if stop["port_free"] else {"ok": False}
    checks = {
        "stop_frees_port": _check(stop["port_free"], stop_s=stop["stop_s"]),
        **_down_checks(ctx, down),
        "exclusive_workspace_fails_fast": _check(
            bool(down.get("exclusive_workspace", {}).get("definite")),
            row=down.get("exclusive_workspace"),
        ),
        "reload_serves_again": _check(bool(first.get("ok")), row=first),
    }
    return _item(
        "lifecycle",
        "the Pipeline can unload and reload the candidate (process stop + restart), the seat's "
        "production route and its Ollama fallback answer while it is down, and the reload serves",
        checks,
        {
            "stop": stop,
            "down": down,
            "restart": restart,
            "cold_load_s": restart.get("ready_s"),
            "reload_first_request_s": first.get("elapsed_s"),
            "incumbent_control": {
                "engine": "omlx",
                "unload": "POST /admin/api/models/{id}/unload (load_guard) and "
                "POST /v1/models/{id}/unload (harness pre-canary unload)",
                "reload": "the next request loads the model; there is no explicit load route",
                "candidate_control": "no HTTP unload route: stop the owned process group "
                "(SIGINT, then SIGTERM) and relaunch the registry argv",
                "source": "portal/platform/inference/load_guard.py and "
                "tests/benchmarks/engine_eval_runner.py:_unload_production_model",
            },
            "notes": [
                "the bench-engine-* workspaces are exclusive (config/bench_engines.yaml "
                "exclusive_workspaces): while the candidate is down a pinned request returns an "
                "error instead of falling through to production",
                "the seat users reach is production_route; that is the fallback this cell proves",
            ],
        },
    )


def _backend_entry(ctx: dict[str, Any]) -> dict[str, Any] | None:
    data = yaml.safe_load(BENCH_ENGINES.read_text(encoding="utf-8")) or {}
    backend = str(ctx["cell"]["backend"])
    return next((entry for entry in data.get("backends") or [] if entry.get("id") == backend), None)


def _resolve_program(argv: list[str], cwd: str | None) -> dict[str, Any]:
    if not argv:
        return {"path": None, "error": "empty argv"}
    program = argv[0]
    if "/" in program:
        path = Path(program).expanduser()
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
    else:
        found = shutil.which(program)
        path = Path(found) if found else None
    if path is None or not path.exists():
        return {"path": str(path) if path else program, "error": f"{program} does not resolve"}
    return {"path": str(path.resolve()), "error": None}


def _launchd_check(ctx: dict[str, Any]) -> dict[str, Any]:
    """A plist launchd could load: absolute program, KeepAlive, absolute logs."""
    cell = ctx["cell"]
    resolved = _resolve_program(cell.get("argv") or [], cell.get("cwd"))
    argv = list(cell.get("argv") or [])
    placeholders = [arg for arg in argv if _PLACEHOLDER.search(arg)]
    program = resolved["path"] or ""
    argv = [program, *argv[1:]] if program else argv
    logs = ctx["dir"] / "launchd"
    plist = {
        "Label": f"com.portal5.engine-prodfit.{cell['engine']}",
        "ProgramArguments": argv,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(logs / f"{cell['engine']}.out.log"),
        "StandardErrorPath": str(logs / f"{cell['engine']}.err.log"),
        "ThrottleInterval": 30,
    }
    if cell.get("cwd"):
        plist["WorkingDirectory"] = str(cell["cwd"])
    path = ctx["dir"] / f"{ctx['cell_id']}.launchd.plist"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(plist))
    lint = _command(["plutil", "-lint", "-s", str(path)])
    checks = {
        "program_absolute": _check(
            bool(program) and Path(program).is_absolute() and not resolved["error"],
            program=program,
            resolve_error=resolved["error"],
        ),
        "argv_rendered": _check(not placeholders, unrendered=placeholders),
        "fixed_port": _check(
            "--port" in argv or any(k in argv for k in ("-p",)), port=cell["port"]
        ),
        "plist_lints": _check(lint.strip() == "", plutil=lint.strip() or "ok"),
    }
    return _item(
        "operations-launchd",
        "the registry argv is launchd-expressible with KeepAlive and log paths, and the "
        "generated plist passes plutil -lint (not installed)",
        checks,
        {"plist": str(path), "plist_body": plist, "argv": argv},
    )


def _health_ids(payload: dict[str, Any]) -> list[str]:
    """Ids from the OpenAI ``data`` list or the engine's own ``models`` list."""
    ids = [
        str(item.get("id"))
        for item in payload.get("data") or []
        if isinstance(item, dict) and item.get("id")
    ]
    for item in payload.get("models") or []:
        name = item.get("id") or item.get("name") if isinstance(item, dict) else item
        if name:
            ids.append(str(name))
    return ids


def _health_check(ctx: dict[str, Any], entry: dict[str, Any] | None) -> dict[str, Any]:
    path = str((entry or {}).get("health_path") or "/v1/models")
    url = f"{str(ctx['cell']['base']).rstrip('/')}{path}"
    sent = _http(url, headers=h2h._headers(url))
    ids = _health_ids(sent.get("json") or {})
    served_set = (entry or {}).get("listing_is_served_set", True) is not False
    expected = {str(ctx["cell"]["expected_model"]), str(ctx["cell"].get("listed_model") or "")}
    resolves = bool(expected & set(ids)) if ids else None
    checks = {
        "answers_200": _check(sent["status"] == 200, status=sent["status"], error=sent["error"]),
        "seat_id_resolves_or_listing_not_served_set": _check(
            (resolves is True)
            or (resolves is False and not served_set)
            or (resolves is None and not served_set),
            listing_resolves_seat=resolves,
            listing_is_served_set=served_set,
        ),
    }
    return _item(
        "operations-health",
        "the registry health_path answers HTTP 200 and resolves the seat id (or the listing is "
        "declared not to be the served set)",
        checks,
        {"url": url, "status": sent["status"], "ids": ids[:20], "error": sent["error"]},
    )


def _version_check(ctx: dict[str, Any], entry: dict[str, Any] | None) -> dict[str, Any]:
    ident = h2h.engine_identity(ctx["cfg"], ctx["cell"]["engine"], ctx["cell"].get("argv"))
    channel = (ctx["block"].get("autoupdate_channels") or {}).get(ctx["cell"]["engine"]) or {}
    checks = {
        "version_probe_ok": _check(ident.get("ok") is True, reason=ident.get("reason")),
        "version_parsed": _check(bool(ident.get("installed")), installed=ident.get("installed")),
        "install_channel_declared": _check(
            bool(channel.get("channel")),
            channel=channel.get("channel"),
        ),
    }
    return _item(
        "operations-version",
        "a non-interactive probe returns a parseable version and the engine has a declared "
        "install channel engine_autoupdate can be given a provider for",
        checks,
        {
            "identity": ident,
            "autoupdate_channel": channel,
            "engine_autoupdate_covered": False,
            "coverage_note": "scripts/engine_autoupdate.py covers ollama and omlx only; a "
            "candidate needs a provider before the weekly job can drive it",
            "backend_entry": entry.get("id") if entry else None,
        },
    )


def _running_executable(port: int) -> dict[str, Any]:
    """The executable of the process actually serving the cell's port."""
    pid = h2h.pid_on_port(port)
    if not pid:
        return {"pid": None, "executable": None}
    return {
        "pid": pid,
        "executable": _command(["ps", "-p", str(pid), "-o", "comm="]).strip() or None,
    }


def _launch_chain(program: str | None) -> list[dict[str, str]]:
    """``file`` on the program and, for a script wrapper, its shebang interpreter."""
    readings: list[dict[str, str]] = []
    target = program
    for _depth in range(2):
        if not target or not Path(target).exists():
            break
        text = _command(["file", "-b", target])
        readings.append({"path": target, "file": text})
        if "Mach-O" in text:
            break
        target = h2h._script_interpreter(target)
    return readings


def _arm64(readings: list[dict[str, str]]) -> bool:
    """Every Mach-O in the chain is arm64 (or universal), and at least one was read."""
    macho = [row for row in readings if "Mach-O" in row["file"]]
    return bool(macho) and all(
        "arm64" in row["file"] or "universal" in row["file"] for row in macho
    )


def _arch_check(ctx: dict[str, Any]) -> dict[str, Any]:
    """arm64 must hold for the executable that serves the seat, not just the launcher."""
    running = _running_executable(int(ctx["cell"]["port"]))
    running_readings = _launch_chain(running["executable"])
    launcher = _resolve_program(ctx["cell"].get("argv") or [], ctx["cell"].get("cwd"))
    launcher_readings = _launch_chain(launcher["path"])
    machine = platform.machine()
    return _item(
        "operations-arm64",
        "host is arm64, the launcher chain is arm64, and the executable serving the seat is an "
        "arm64 Mach-O or a universal build",
        {
            "host_arm64": _check(machine == "arm64", machine=machine),
            "launcher_arm64": _check(
                _arm64(launcher_readings),
                readings=launcher_readings,
                launcher=launcher["path"],
                launcher_error=launcher["error"],
            ),
            "engine_executable_arm64": _check(
                _arm64(running_readings), running=running, readings=running_readings
            ),
        },
        {"launcher": launcher, "running": running},
    )


def _port(url: str) -> int | None:
    try:
        return urlsplit(url).port
    except ValueError:
        return None


def _config_check(ctx: dict[str, Any], entry: dict[str, Any] | None) -> dict[str, Any]:
    """The registry entry must stay expressible as a config/backends.yaml backend."""
    data = yaml.safe_load(BENCH_ENGINES.read_text(encoding="utf-8")) or {}
    ports = sorted(
        {port for item in data.get("backends") or [] if (port := _port(str(item.get("url"))))}
    )
    entry = entry or {}
    url = str(entry.get("url") or "")
    models = [
        str(model.get("id")) for model in entry.get("models") or [] if isinstance(model, dict)
    ]
    expected = {str(ctx["cell"]["expected_model"]), str(ctx["cell"].get("listed_model") or "")}
    checks = {
        "entry_exists": _check(bool(entry.get("id")), backend=ctx["cell"]["backend"]),
        "url_and_health_path": _check(
            bool(url) and bool(entry.get("health_path")),
            url=url,
            health_path=entry.get("health_path"),
        ),
        "port_matches_registry": _check(
            _port(url) == int(ctx["cell"]["port"]),
            url_port=_port(url),
            registry_port=ctx["cell"]["port"],
        ),
        "eval_port_reserved": _check(int(ctx["cell"]["port"]) in ports, eval_ports=ports),
        "model_listed": _check(bool(expected & set(models)), models=models),
    }
    return _item(
        "operations-config",
        "the candidate is a config/backends.yaml-shaped entry: url, health_path, reserved eval "
        "port matching the registry, and the seat's model id in models",
        checks,
        {"backend": entry.get("id"), "type": entry.get("type"), "group": entry.get("group")},
    )


def _operations(ctx: dict[str, Any]) -> dict[str, Any]:
    entry = _backend_entry(ctx)
    items = {
        "launchd": _launchd_check(ctx),
        "health": _health_check(ctx, entry),
        "version": _version_check(ctx, entry),
        "arm64": _arch_check(ctx),
        "config": _config_check(ctx, entry),
    }
    return {
        "item": "operations",
        "status": _status(all(item["valid"] for item in items.values())),
        "valid": all(item["valid"] for item in items.values()),
        "pass_rule": "every operations checklist item passes with its own evidence",
        "checklist": items,
        "failed": [name for name, item in items.items() if not item["valid"]],
    }


def _safe_step(func, ctx: dict[str, Any]) -> dict[str, Any]:
    try:
        return func(ctx)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, SystemExit) as exc:
        return {
            "item": getattr(func, "__name__", "step"),
            "status": "FAIL",
            "valid": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "checks": {},
            "evidence": {},
        }


def _ensure_stopped(ctx: dict[str, Any]) -> dict[str, Any]:
    cell = ctx["cell"]
    try:
        if h2h.pid_on_port(int(cell["port"])):
            return _stop_candidate(ctx)
    except (OSError, subprocess.SubprocessError, SystemExit) as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "port_free": False}
    return {"port_free": True, "stop_s": 0.0}


def _receipt_head(ctx: dict[str, Any]) -> dict[str, Any]:
    cell = ctx["cell"]
    return {
        "build": ctx["build"],
        "created_at": _now(),
        "cell": {
            key: cell.get(key)
            for key in (
                "engine",
                "mode",
                "seat",
                "model",
                "model_hint",
                "workspace",
                "backend",
                "port",
            )
        },
        "cell_id": ctx["cell_id"],
        "pipeline": ctx["pipeline"],
        "production_seat": ctx["seat_is_production"],
        "production_seats": ctx["block"]["production_seats"],
        "other_production_seats": [
            {"seat": target["seat"], "model": target["model"]} for target in ctx["others"]
        ],
    }


def _write_receipt(ctx: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    path = ctx["receipt"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt["receipt"] = str(path)
    print(
        json.dumps(
            {
                "cell": receipt["cell_id"],
                "verdict": receipt["verdict"],
                "failed_items": receipt.get("failed_items", []),
                "receipt": receipt["receipt"],
            },
            indent=2,
        ),
        flush=True,
    )
    return receipt


def _blocked_receipt(ctx: dict[str, Any], reason: str) -> dict[str, Any]:
    return _write_receipt(
        ctx,
        {
            **_receipt_head(ctx),
            "verdict": "BLOCKED",
            "reason": reason,
            "failed_items": ["preflight"],
        },
    )


def _finish(ctx: dict[str, Any], started: dict[str, Any], items: dict[str, Any]) -> dict[str, Any]:
    receipt = {
        **_receipt_head(ctx),
        "start": started,
        "co_residence": items["co_residence"],
        "lifecycle": items["lifecycle"],
        "operations": items["operations"],
        "shutdown": items["shutdown"],
        "verdict": "PASS" if all(v.get("valid") is True for v in items.values()) else "FAIL",
        "failed_items": [name for name, item in items.items() if item.get("valid") is not True],
    }
    return _write_receipt(ctx, receipt)


def _shutdown_item(stop: dict[str, Any]) -> dict[str, Any]:
    valid = stop.get("port_free") is True
    return {
        "item": "shutdown",
        "status": _status(valid),
        "valid": valid,
        "pass_rule": "the candidate is stopped and its port is free at the end of the run",
        "reason": None if valid else f"candidate port still held: {stop.get('listener')}",
        "checks": {"port_free": _check(valid, listener=stop.get("listener"))},
        "evidence": stop,
    }


def run_prodfit(
    cell: dict[str, Any],
    pipeline: str,
    *,
    build: str,
    root: Path,
) -> dict[str, Any]:
    """Judge one installed cell's production fit and write its receipt."""
    ctx = _context(cell, pipeline, build, root)
    blocker = cell.get("launch_error") or cell.get("not_installed")
    if blocker:
        return _blocked_receipt(ctx, str(blocker))
    with h2h.single_flight():
        ctx["pre_candidate"] = _safe_step(_warm_production, ctx)
        started = _safe_step(_start_candidate, ctx)
        items: dict[str, Any] = {}
        try:
            items["co_residence"] = _safe_step(_co_residence, ctx)
            items["operations"] = _safe_step(_operations, ctx)
            items["lifecycle"] = _safe_step(_lifecycle, ctx)
        finally:
            items["shutdown"] = _shutdown_item(_safe_step(_ensure_stopped, ctx))
    return _finish(ctx, started, items)
