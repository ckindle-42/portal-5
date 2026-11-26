"""Inter-phase gate: pipeline health, engine health + residency-aware
eviction, host memory guard, MLX media pressure report.

Eviction is residency-checked: oMLX 0.8.1 returns HTTP 400 for an unload of
an already-cold model, so residency is read from /v1/models/status (falling
back to /v1/models/loaded) and only resident models are unloaded. The unload
itself is asynchronous (HTTP 202): the gate polls residency for
OMLX_EVICT_SETTLE_S before reporting PASS, since Metal memory is reclaimed
over the next seconds. Ollama keep_alive 0 is asynchronous too: /api/ps is
polled until release progress stalls or confirms the model is gone. The retained
MLX media services (mlx-speech :8918,
mflux :8933, video-mlx :8935) are memory-pressure reporters only — never killed.
"""

from __future__ import annotations

import fcntl
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from .config import DEFAULT_MEM_CAP_PCT, Settings
from .models import GateReport, QATResult, Status

MEDIA_SERVICES: tuple[tuple[str, str, int], ...] = (
    ("mlx-speech", "http://localhost:8918/health", 8918),
    ("mflux", "http://localhost:8933/health", 8933),
    ("video-mlx", "http://localhost:8935/health", 8935),
)
# Idle windows for inter-phase resource admission. Each is reset by a resident
# model leaving or by a measurable drop in host memory use. They are not total
# wall-clock budgets for a gate that is still making progress.
WAIT_BUDGET_S = 600.0
POLL_S = 15.0
EVICT_SETTLE_S = 2.0
#: Over cap with nothing resident: fail only after memory use has made no
#: measurable progress for this idle window.
MEMORY_HOLD_BUDGET_S = 120.0
MEMORY_HOLD_POLL_S = 15.0
#: Heuristic name match for engine-side RSS holders (ollama/oMLX/MLX media).
ENGINE_PROC_PAT = re.compile(r"ollama|omlx|mlx|mflux|ltx|llama", re.IGNORECASE)
#: Idle window for residency release after an accepted async unload.
OMLX_EVICT_IDLE_TIMEOUT_S = 300.0
OMLX_EVICT_SETTLE_STEP_S = 0.5
#: Short /api/generate → loaded-runners drop, ollama.log n=78: p50 12.6s, p95 42.2s, max 50.2s.
OLLAMA_EVICT_IDLE_TIMEOUT_S = 300.0
OLLAMA_EVICT_POLL_S = 0.5


def _get(client: httpx.Client, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.get(url, headers=headers or {}, timeout=10.0)


def pipeline_health(client: httpx.Client, settings: Settings) -> QATResult:
    """/health must answer ok with backends_checked=true (backend liveness done)."""
    try:
        r = _get(client, f"{settings.pipeline_url}/health")
        body = r.json()
    except Exception as exc:
        return QATResult("gate-pipeline", Status.FAIL, f"pipeline /health unreachable: {exc}")
    checked = bool(body.get("backends_checked"))
    healthy = int(body.get("backends_healthy", 0) or 0)
    total = int(body.get("backends_total", 0) or 0)
    if r.status_code != 200 or body.get("status") not in ("ok", "degraded"):
        return QATResult("gate-pipeline", Status.FAIL, f"HTTP {r.status_code} {body}")
    if not checked:
        return QATResult(
            "gate-pipeline", Status.FAIL, "backends_checked=false — registry not ready"
        )
    status = Status.PASS if body.get("status") == "ok" else Status.WARN
    return QATResult(
        "gate-pipeline",
        status,
        f"backends {healthy}/{total} healthy",
        evidence={"body": body},
    )


def ollama_residency(client: httpx.Client, settings: Settings) -> tuple[QATResult, list[str]]:
    """Ollama health (/api/tags) plus resident models (/api/ps)."""
    try:
        r = _get(client, f"{settings.ollama_url}/api/tags")
        if r.status_code != 200:
            return QATResult("gate-ollama", Status.FAIL, f"/api/tags HTTP {r.status_code}"), []
        ps = _get(client, f"{settings.ollama_url}/api/ps")
        names = [str(m.get("name", "")) for m in ps.json().get("models", [])]
    except Exception as exc:
        return QATResult("gate-ollama", Status.FAIL, f"Ollama unreachable: {exc}"), []
    status = Status.PASS if not names else Status.WARN
    detail = "reachable, nothing resident" if not names else f"resident: {', '.join(names)}"
    return QATResult("gate-ollama", status, detail, evidence={"resident": names}), names


def _omlx_instance_key(model: dict) -> tuple[str, ...]:
    model_id = str(model.get("id") or model.get("name") or "")
    model_path = str(model.get("model_path") or "")
    if not model_path:
        return ("id", model_id)
    adapter_config = model.get("adapter_config")
    adapter_key = (
        json.dumps(adapter_config, sort_keys=True, default=str)
        if adapter_config is not None
        else ""
    )
    engine = str(model.get("engine_type") or model.get("engine") or "")
    return ("path", model_path, engine, adapter_key)


def _omlx_instance_id(models: list[dict]) -> str:
    source_id = next(
        (str(model["source_model_id"]) for model in models if model.get("source_model_id")), ""
    )
    if source_id:
        return source_id
    ids = [str(model.get("id") or model.get("name") or "") for model in models]
    model_path = str(models[0].get("model_path") or "")
    base_id = PurePosixPath(model_path).name if model_path else ""
    return base_id if base_id in ids else ids[0]


def _omlx_resident_instances(models: list[dict]) -> list[str]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id") or model.get("name") or "")
        if model_id:
            groups.setdefault(_omlx_instance_key(model), []).append(model)
    return [_omlx_instance_id(group) for group in groups.values()]


def omlx_residency(client: httpx.Client, settings: Settings) -> tuple[QATResult, list[str]]:
    """Read oMLX residency from /v1/models/status, then /v1/models/loaded."""
    headers = settings.omlx_headers()
    errors: list[str] = []
    for path in ("/v1/models/status", "/v1/models/loaded"):
        try:
            r = _get(client, f"{settings.omlx_url}{path}", headers)
            if r.status_code != 200:
                detail = r.text.strip()[:240]
                errors.append(f"{path} HTTP {r.status_code}" + (f": {detail}" if detail else ""))
                continue
            body = r.json()
            models = body.get("models", body.get("data", []))
            if path == "/v1/models/status":
                models = [
                    model
                    for model in models
                    if isinstance(model, dict)
                    and model.get("loaded") is True
                    and str(model.get("id") or model.get("name") or "").lower() != "markitdown"
                ]
            names = _omlx_resident_instances(models)
            status = Status.PASS if not names else Status.WARN
            detail = "reachable, cold" if not names else f"resident: {', '.join(names)}"
            return QATResult("gate-omlx", status, detail, evidence={"resident": names}), names
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
    detail = "; ".join(errors) or "no readable residency endpoint"
    return QATResult(
        "gate-omlx", Status.FAIL, f"oMLX residency endpoints unreachable: {detail}"
    ), []


def evict_ollama(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    """Unload idle residents and stop waiting only after release progress stalls."""
    active = [name for name in resident if _pipeline_ollama_in_flight(name)]
    if active:
        return QATResult(
            "gate-evict",
            Status.BLOCKED,
            f"Ollama unload skipped while model requests are active: {active}",
            evidence={"resident": active, "state": "in_flight"},
        )
    started = time.monotonic()
    blocked = _request_ollama_unload(client, settings, resident)
    if isinstance(blocked, QATResult):
        return blocked
    return _wait_ollama_unloaded(client, settings, resident, started, blocked)


def _request_ollama_unload(
    client: httpx.Client, settings: Settings, resident: list[str]
) -> QATResult | set[str]:
    """POST keep_alive 0. A timeout means the request is queued behind in-flight work."""
    blocked: set[str] = set()
    for name in resident:
        try:
            response = client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": name, "keep_alive": 0},
                timeout=15.0,
            )
        except httpx.TimeoutException:
            blocked.add(name)
            continue
        except Exception as exc:
            return QATResult("gate-evict", Status.FAIL, f"Ollama evict {name}: {exc}")
        if not response.is_success:
            return QATResult(
                "gate-evict", Status.FAIL, f"Ollama evict {name}: HTTP {response.status_code}"
            )
    return blocked


def _wait_ollama_unloaded(
    client: httpx.Client,
    settings: Settings,
    resident: list[str],
    started: float,
    blocked: set[str],
) -> QATResult:
    seen: set[str] = set()
    if blocked:
        seen.add("in_flight")
    last_state: dict[str, str] = dict.fromkeys(blocked, "in_flight")
    last_expiry: dict[str, str] = {}
    previous_expiry: dict[str, datetime] = {}
    last_signature: tuple[tuple[str, str, str, bool], ...] | None = None
    idle_deadline = time.monotonic() + OLLAMA_EVICT_IDLE_TIMEOUT_S
    while True:
        models, error = _read_ollama_ps(client, settings)
        if error is not None:
            return error
        if not models:
            return _ollama_evict_pass(len(resident), time.monotonic() - started, seen)
        for model in models:
            name = str(model.get("name") or "")
            last_expiry[name] = str(model.get("expires_at") or "")
            state = _ollama_release_state(name, model, previous_expiry.get(name), name in blocked)
            last_state[name] = state
            seen.add(state)
            parsed = _expires_at(model.get("expires_at"))
            if parsed is not None:
                previous_expiry[name] = parsed
        signature = tuple(
            sorted(
                (
                    str(model.get("name") or ""),
                    last_state.get(str(model.get("name") or ""), ""),
                    last_expiry.get(str(model.get("name") or ""), ""),
                    _pipeline_ollama_in_flight(str(model.get("name") or "")),
                )
                for model in models
            )
        )
        if signature != last_signature:
            last_signature = signature
            idle_deadline = time.monotonic() + OLLAMA_EVICT_IDLE_TIMEOUT_S
        if time.monotonic() >= idle_deadline:
            return _ollama_evict_stuck(models, last_state, last_expiry, time.monotonic() - started)
        _poll_pause(OLLAMA_EVICT_POLL_S)


def _read_ollama_ps(
    client: httpx.Client, settings: Settings
) -> tuple[list[dict[str, object]] | None, QATResult | None]:
    try:
        response = _get(client, f"{settings.ollama_url}/api/ps")
    except Exception as exc:
        return None, QATResult("gate-evict", Status.FAIL, f"Ollama residency check failed: {exc}")
    if response.status_code != 200:
        return None, QATResult(
            "gate-evict", Status.FAIL, f"Ollama residency check failed: HTTP {response.status_code}"
        )
    try:
        body = response.json()
    except Exception as exc:
        return None, QATResult("gate-evict", Status.FAIL, f"Ollama residency check failed: {exc}")
    models = body.get("models", [])
    if not isinstance(models, list):
        return None, QATResult(
            "gate-evict", Status.FAIL, "Ollama residency check failed: no models"
        )
    return [model for model in models if isinstance(model, dict)], None


def _ollama_release_state(
    name: str,
    model: dict[str, object],
    previous: datetime | None,
    unload_blocked: bool,
) -> str:
    """in_flight while a request holds the model; otherwise the runner is releasing."""
    if unload_blocked or _pipeline_ollama_in_flight(name):
        return "in_flight"
    expires = _expires_at(model.get("expires_at"))
    if previous is not None and expires is not None and expires > previous + timedelta(seconds=1):
        return "in_flight"
    return "releasing"


def _pipeline_ollama_in_flight(name: str) -> bool:
    """True when a pipeline worker holds this model's load-guard activity lock."""
    return _pipeline_model_in_flight("ollama", name)


def _pipeline_model_in_flight(engine: str, name: str) -> bool:
    """True when a pipeline worker holds this engine model's activity lock."""
    if not name:
        return False
    from portal.platform.inference.load_guard import LoadGuard

    path = LoadGuard._activity_path(engine, name)
    if not path.is_file():
        return False
    try:
        handle = path.open("a+")
    except OSError:
        return True
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return True
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


def _expires_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _state_summary(states: set[str]) -> str:
    return ", ".join(sorted(states)) if states else "releasing"


def _ollama_evict_pass(count: int, elapsed: float, seen: set[str]) -> QATResult:
    detail = f"evicted {count} Ollama model(s)"
    if seen:
        detail += f" in {elapsed:.1f}s ({_state_summary(seen)})"
    return QATResult(
        "gate-evict",
        Status.PASS,
        detail,
        evidence={
            "waited_s": round(elapsed, 3),
            "state": _state_summary(seen),
            "idle_timeout_s": OLLAMA_EVICT_IDLE_TIMEOUT_S,
        },
    )


def _ollama_evict_stuck(
    models: list[dict[str, object]],
    last_state: dict[str, str],
    last_expiry: dict[str, str],
    elapsed: float,
) -> QATResult:
    names = [str(model.get("name") or "") for model in models]
    summary = _state_summary(set(last_state.values()))
    return QATResult(
        "gate-evict",
        Status.FAIL,
        (
            f"Ollama release made no progress for {OLLAMA_EVICT_IDLE_TIMEOUT_S:.0f}s "
            f"after {elapsed:.1f}s ({summary}): {names}"
        ),
        evidence={
            "resident": names,
            "state": dict(last_state),
            "expires_at": dict(last_expiry),
            "waited_s": round(elapsed, 3),
            "idle_timeout_s": OLLAMA_EVICT_IDLE_TIMEOUT_S,
        },
    )


def _poll_pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _unload_omlx_one(
    client: httpx.Client, settings: Settings, name: str
) -> tuple[QATResult | None, bool]:
    """Issue one unload; return a failure row and whether 404 proved it cold."""
    encoded = quote(name, safe=":")
    try:
        response = client.post(
            f"{settings.omlx_url}/admin/api/models/{encoded}/unload",
            headers=settings.omlx_headers(),
            timeout=15.0,
        )
        if response.status_code == 404:
            response = client.post(
                f"{settings.omlx_url}/v1/models/{encoded}/unload",
                headers=settings.omlx_headers(),
                timeout=15.0,
            )
    except Exception as exc:
        return QATResult("gate-evict-omlx", Status.FAIL, f"unload {name}: {exc}"), False
    if response.status_code == 404:
        residency, names = omlx_residency(client, settings)
        reason = response.text.strip() or "empty response body"
        if residency.status is Status.FAIL:
            return (
                QATResult(
                    "gate-evict-omlx",
                    Status.FAIL,
                    f"unload {name}: HTTP 404 ({reason}); residency check failed: {residency.detail}",
                ),
                False,
            )
        if name in names:
            return (
                QATResult(
                    "gate-evict-omlx",
                    Status.FAIL,
                    f"unload {name}: HTTP 404 ({reason}); model is still resident",
                ),
                False,
            )
        return None, True
    if response.status_code not in (200, 202, 204, 400):
        reason = response.text.strip()
        detail = f"unload {name}: HTTP {response.status_code}"
        return QATResult(
            "gate-evict-omlx", Status.FAIL, detail + (f" ({reason})" if reason else "")
        ), False
    return None, False


def evict_omlx(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    """Unload residency-confirmed models, then wait for async unload completion."""
    already_cold: list[str] = []
    for name in resident:
        if _pipeline_model_in_flight("omlx", name):
            return QATResult(
                "gate-evict-omlx",
                Status.BLOCKED,
                f"oMLX unload skipped while a model request is active: {name}",
                evidence={"resident": [name], "state": "in_flight"},
            )
        failure, was_cold = _unload_omlx_one(client, settings, name)
        if failure is not None:
            return failure
        if was_cold:
            already_cold.append(name)
    if not resident:
        return QATResult("gate-evict-omlx", Status.PASS, "oMLX already cold")
    idle_deadline = time.monotonic() + OMLX_EVICT_IDLE_TIMEOUT_S
    previous_state: tuple[Status, tuple[str, ...]] | None = None
    while True:
        result, names = omlx_residency(client, settings)
        state = (result.status, tuple(names))
        if state != previous_state:
            previous_state = state
            idle_deadline = time.monotonic() + OMLX_EVICT_IDLE_TIMEOUT_S
        stuck = [n for n in names if n in resident]
        if not stuck and result.status is not Status.FAIL:
            detail = f"evicted {len(resident)} oMLX model(s)"
            if already_cold:
                detail += f"; 404 confirmed cold: {', '.join(already_cold)}"
            return QATResult("gate-evict-omlx", Status.PASS, detail)
        if time.monotonic() >= idle_deadline:
            detail = (
                f"unload accepted but model still resident; residency made no progress for "
                f"{OMLX_EVICT_IDLE_TIMEOUT_S:.0f}s: {stuck}"
                if stuck
                else "eviction unconfirmed: residency is unreadable"
            )
            return QATResult(
                "gate-evict-omlx",
                Status.FAIL,
                detail,
                evidence={
                    "resident": resident,
                    "idle_timeout_s": OMLX_EVICT_IDLE_TIMEOUT_S,
                },
            )
        time.sleep(OMLX_EVICT_SETTLE_STEP_S)


def vm_memory() -> QATResult:
    """macOS unified-memory snapshot from vm_stat; SKIP on non-darwin hosts."""
    if sys.platform != "darwin":
        return QATResult("gate-memory", Status.SKIP, f"vm_stat unavailable on {sys.platform}")
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
        used_pct, _free_gb = parse_vm_stat(out)
    except (OSError, ValueError) as exc:
        return QATResult("gate-memory", Status.SKIP, f"vm_stat parse failed: {exc}")
    if used_pct < 0:
        return QATResult("gate-memory", Status.SKIP, "vm_stat reported no page counts")
    status = Status.PASS if used_pct < DEFAULT_MEM_CAP_PCT else Status.WARN
    return QATResult(
        "gate-memory", status, f"used {used_pct:.1f}% (cap {DEFAULT_MEM_CAP_PCT:.0f}%)"
    )


def parse_vm_stat(out: str) -> tuple[float, float]:
    """(used_pct, free_gb) from vm_stat text; M-series pages are 16384 B.

    Compressor pages stay in the denominator: excluding them made
    (active+wired)/total overstate usage on compressed-heavy hosts. An empty
    total is unreadable (-1.0), never a fabricated 99%.
    """
    pages: dict[str, int] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits:
            pages[key.strip()] = int(digits)
    total_keys = (
        "Pages free",
        "Pages active",
        "Pages inactive",
        "Pages speculative",
        "Pages wired down",
        "Pages occupied by compressor",
    )
    total = sum(pages.get(k, 0) for k in total_keys)
    if total == 0:
        return -1.0, 0.0
    used = sum(pages.get(k, 0) for k in ("Pages active", "Pages wired down"))
    page = 16384
    return used / total * 100.0, pages.get("Pages free", 0) * page / 1024**3


def memory_holders(limit: int = 10) -> dict[str, object]:
    """Top RSS processes split engine vs non-engine; empty off-darwin or on error."""
    if sys.platform != "darwin":
        return {}
    try:
        proc = subprocess.run(
            ["ps", "-axo", "rss=,comm="], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    entries: list[tuple[int, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            entries.append((int(parts[0]), parts[1]))
    if not entries:
        return {}
    entries.sort(key=lambda entry: -entry[0])
    engine_kb = sum(rss for rss, name in entries if ENGINE_PROC_PAT.search(name))
    total_kb = sum(rss for rss, _ in entries)
    return {
        "top_rss": [
            {
                "process": PurePosixPath(name).name,
                "rss_mb": round(rss / 1024, 1),
                "engine": bool(ENGINE_PROC_PAT.search(name)),
            }
            for rss, name in entries[:limit]
        ],
        "engine_rss_mb": round(engine_kb / 1024, 1),
        "non_engine_rss_mb": round((total_kb - engine_kb) / 1024, 1),
    }


def _holder_summary(holders: dict[str, object]) -> str:
    top = holders.get("top_rss")
    if not isinstance(top, list):
        return ""
    return ", ".join(
        f"{p['process']} {p['rss_mb']:.0f}MB {'engine' if p['engine'] else 'non-engine'}"
        for p in top[:3]
        if isinstance(p, dict)
    )


def media_pressure(client: httpx.Client) -> QATResult:
    """Report retained MLX media services as pressure sources — never kill."""
    up: list[str] = []
    for name, url, port in MEDIA_SERVICES:
        try:
            r = _get(client, url)
            if r.status_code < 500:
                up.append(f"{name}(:{port})")
        except Exception:
            continue
    detail = f"retained pressure sources: {', '.join(up)}" if up else "no MLX media service up"
    return QATResult("gate-media-pressure", Status.PASS, detail)


def _observe_gate_progress(
    wait: bool,
    now: float,
    resident_state: tuple[str, ...],
    used_pct: float,
    previous_residents: tuple[str, ...] | None,
    previous_used_pct: float | None,
    wait_deadline: float,
    hold_deadline: float,
) -> tuple[float, float]:
    """Restart both wait windows after observable residency or memory progress."""
    resident_progress = previous_residents is not None and resident_state != previous_residents
    memory_progress = (
        previous_used_pct is not None
        and previous_used_pct >= 0
        and used_pct >= 0
        and used_pct < previous_used_pct - 0.05
    )
    if wait and (resident_progress or memory_progress):
        return now + WAIT_BUDGET_S, now + MEMORY_HOLD_BUDGET_S
    return wait_deadline, hold_deadline


def _evict_residents(
    client: httpx.Client, settings: Settings, ollama: list[str], omlx: list[str]
) -> tuple[list[QATResult], bool]:
    """Attempt unloads for every resident engine and report whether work was issued."""
    checks: list[QATResult] = []
    if ollama:
        checks.append(evict_ollama(client, settings, ollama))
    if omlx:
        checks.append(evict_omlx(client, settings, omlx))
    return checks, bool(ollama or omlx)


def _residency_loop(
    client: httpx.Client, settings: Settings, checks: list[QATResult], wait: bool, started: float
) -> tuple[list[QATResult], float, int, float]:
    """Evict residents until clean, failing waits only after observable progress stalls."""
    used_pct = -1.0
    resident_total = -1
    hold_waited_s = 0.0
    hold_start: float | None = None
    rerun_ids = ("gate-ollama", "gate-omlx", "gate-memory")
    now = max(started, time.monotonic())
    wait_idle_deadline = now + (WAIT_BUDGET_S if wait else 0.0)
    hold_idle_deadline = now + (MEMORY_HOLD_BUDGET_S if wait else 0.0)
    previous_residents: tuple[str, ...] | None = None
    previous_used_pct: float | None = None
    confirmed_once = False
    while True:
        ol, ol_resident = ollama_residency(client, settings)
        ox, ox_resident = omlx_residency(client, settings)
        mem = vm_memory()
        used_pct = _used_from_detail(mem.detail)
        resident_state = tuple(sorted(ol_resident)) + tuple(sorted(ox_resident))
        now = time.monotonic()
        wait_idle_deadline, hold_idle_deadline = _observe_gate_progress(
            wait,
            now,
            resident_state,
            used_pct,
            previous_residents,
            previous_used_pct,
            wait_idle_deadline,
            hold_idle_deadline,
        )
        previous_residents = resident_state
        previous_used_pct = used_pct
        checks = [c for c in checks if c.scenario_id not in rerun_ids] + [ol, ox, mem]
        resident_total = len(ol_resident) + len(ox_resident)
        if not ol_resident and not ox_resident:
            if used_pct < DEFAULT_MEM_CAP_PCT or not wait or now >= hold_idle_deadline:
                if hold_start is not None:
                    hold_waited_s = now - hold_start
                break
            if hold_start is None:
                hold_start = now
            _poll_pause(min(MEMORY_HOLD_POLL_S, max(0.0, hold_idle_deadline - now)))
            continue
        eviction_checks, evicted = _evict_residents(client, settings, ol_resident, ox_resident)
        checks.extend(eviction_checks)
        eviction_failures = [
            check
            for check in checks
            if check.scenario_id in ("gate-evict", "gate-evict-omlx")
            and check.status is not Status.PASS
        ]
        if eviction_failures:
            break
        if evicted and not confirmed_once:
            # one confirmation read even without a wait, so the report
            # reflects the post-eviction state
            confirmed_once = True
            time.sleep(EVICT_SETTLE_S)
            continue
        now = time.monotonic()
        if not wait or now >= wait_idle_deadline:
            break
        time.sleep(min(POLL_S, max(0.0, wait_idle_deadline - now)))
    return checks, used_pct, resident_total, hold_waited_s


def _attach_memory_holders(checks: list[QATResult], hold_waited_s: float) -> None:
    holders = memory_holders()
    summary = _holder_summary(holders)
    for check in checks:
        if check.scenario_id != "gate-memory":
            continue
        check.detail += (
            f"; host busy with: {summary}" if summary else "; host process list unavailable"
        )
        check.evidence = {
            **check.evidence,
            **holders,
            "hold_waited_s": round(hold_waited_s, 1),
            "hold_budget_s": MEMORY_HOLD_BUDGET_S,
        }


def _block_reasons(
    checks: list[QATResult], used_pct: float, resident_total: int
) -> tuple[str, ...]:
    reasons = [f"{c.scenario_id}: {c.detail}" for c in checks if c.status is Status.FAIL]
    if used_pct >= DEFAULT_MEM_CAP_PCT:
        mem = next((c for c in checks if c.scenario_id == "gate-memory"), None)
        if mem is not None:
            reasons.append(f"{mem.scenario_id}: {mem.detail}")
    if resident_total > 0:
        reasons.append(f"{resident_total} model(s) still resident after eviction")
    return tuple(dict.fromkeys(reasons))


def run_gate(
    settings: Settings,
    phase: str,
    transport: httpx.BaseTransport | None = None,
    wait: bool = True,
) -> GateReport:
    """One gate pass; evict until safe or no residency/memory progress remains."""
    started = time.monotonic()
    checks: list[QATResult] = []
    budget_s = WAIT_BUDGET_S if wait else 0.0
    with httpx.Client(transport=transport) as client:
        health = pipeline_health(client, settings)
        checks.append(health)
        if health.status is Status.FAIL:
            return GateReport(
                phase,
                tuple(checks),
                -1.0,
                -1,
                False,
                True,
                waited_s=round(time.monotonic() - started, 3),
                budget_s=budget_s,
                block_reasons=(f"gate-pipeline: {health.detail}",),
            )
        checks, used_pct, resident_total, hold_waited_s = _residency_loop(
            client, settings, checks, wait, started
        )
        checks.append(media_pressure(client))
    if used_pct >= DEFAULT_MEM_CAP_PCT:
        _attach_memory_holders(checks, hold_waited_s)
    block_reasons = _block_reasons(checks, used_pct, resident_total)
    blocked = bool(block_reasons)
    ok = not blocked and all(c.status is Status.PASS for c in checks)
    return GateReport(
        phase,
        tuple(checks),
        used_pct,
        resident_total,
        ok,
        blocked,
        waited_s=round(time.monotonic() - started, 3),
        budget_s=budget_s,
        block_reasons=block_reasons,
    )


def _used_from_detail(detail: str) -> float:
    for token in detail.split():
        if token.endswith("%"):
            try:
                return float(token[:-1])
            except ValueError:
                continue
    return -1.0
