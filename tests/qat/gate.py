"""Inter-phase gate: pipeline health, engine health + residency-aware
eviction, host memory guard, MLX media pressure report.

Eviction is residency-checked: oMLX 0.8.1 returns HTTP 400 for an unload of
an already-cold model, so residency is read from /v1/models/status (falling
back to /v1/models/loaded) and only resident models are unloaded. The unload
itself is asynchronous (HTTP 202): the gate polls residency for
OMLX_EVICT_SETTLE_S before reporting PASS, since Metal memory is reclaimed
over the next seconds. The retained MLX media services (mlx-speech :8918,
mflux :8933, video-mlx :8935) are memory-pressure reporters only — never killed.
"""

from __future__ import annotations

import subprocess
import sys
import time
from urllib.parse import quote

import httpx

from .config import DEFAULT_MEM_CAP_PCT, Settings
from .models import GateReport, QATResult, Status

MEDIA_SERVICES: tuple[tuple[str, str, int], ...] = (
    ("mlx-speech", "http://localhost:8918/health", 8918),
    ("mflux", "http://localhost:8933/health", 8933),
    ("video-mlx", "http://localhost:8935/health", 8935),
)
WAIT_BUDGET_S = 600.0
POLL_S = 15.0
EVICT_SETTLE_S = 2.0
#: oMLX 0.8.1's unload is async (HTTP 202): residency is polled for this window
#: (in OMLX_EVICT_SETTLE_STEP_S steps) before the eviction gate reports PASS.
OMLX_EVICT_SETTLE_S = 10.0
OMLX_EVICT_SETTLE_STEP_S = 0.5


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


def omlx_residency(client: httpx.Client, settings: Settings) -> tuple[QATResult, list[str]]:
    """Read oMLX residency from /v1/models/status, then /v1/models/loaded."""
    headers = settings.omlx_headers()
    for path in ("/v1/models/status", "/v1/models/loaded"):
        try:
            r = _get(client, f"{settings.omlx_url}{path}", headers)
            if r.status_code != 200:
                continue
            body = r.json()
            models = body.get("models", body.get("data", []))
            if path == "/v1/models/status":
                models = [
                    m
                    for m in models
                    if isinstance(m, dict)
                    and m.get("loaded") is True
                    and str(m.get("id") or m.get("name") or "").lower() != "markitdown"
                ]
            names = [str(m.get("id") or m.get("name") or "") for m in models if isinstance(m, dict)]
            names = [n for n in names if n]
            status = Status.PASS if not names else Status.WARN
            detail = "reachable, cold" if not names else f"resident: {', '.join(names)}"
            return QATResult("gate-omlx", status, detail, evidence={"resident": names}), names
        except Exception:
            continue
    return QATResult("gate-omlx", Status.FAIL, "oMLX residency endpoints unreachable"), []


def evict_ollama(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    for name in resident:
        try:
            response = client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": name, "keep_alive": 0},
                timeout=15.0,
            )
            if not response.is_success:
                return QATResult(
                    "gate-evict", Status.FAIL, f"Ollama evict {name}: HTTP {response.status_code}"
                )
        except Exception as exc:
            return QATResult("gate-evict", Status.FAIL, f"Ollama evict {name}: {exc}")
    try:
        response = _get(client, f"{settings.ollama_url}/api/ps")
        remaining = response.json().get("models", []) if response.status_code == 200 else None
    except Exception as exc:
        return QATResult("gate-evict", Status.FAIL, f"Ollama residency check failed: {exc}")
    if remaining is None or remaining:
        names = [str(model.get("name", "")) for model in remaining or []]
        return QATResult("gate-evict", Status.FAIL, f"Ollama models remain resident: {names}")
    return QATResult("gate-evict", Status.PASS, f"evicted {len(resident)} Ollama model(s)")


def evict_omlx(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    """Unload residency-confirmed models through the oMLX admin API, then wait out
    oMLX 0.8.1's async unload (200/202/204): PASS only once residency confirms the
    models are no longer loaded, not at the moment the unload is accepted."""
    for name in resident:
        encoded = quote(name, safe="")
        try:
            r = client.post(
                f"{settings.omlx_url}/admin/api/models/{encoded}/unload",
                headers=settings.omlx_headers(),
                timeout=15.0,
            )
            if r.status_code == 404:
                r = client.post(
                    f"{settings.omlx_url}/v1/models/{encoded}/unload",
                    headers=settings.omlx_headers(),
                    timeout=15.0,
                )
            if r.status_code not in (200, 202, 204, 400):
                return QATResult(
                    "gate-evict-omlx", Status.FAIL, f"unload {name}: HTTP {r.status_code}"
                )
        except Exception as exc:
            return QATResult("gate-evict-omlx", Status.FAIL, f"unload {name}: {exc}")
    if not resident:
        return QATResult("gate-evict-omlx", Status.PASS, "oMLX already cold")
    deadline = time.monotonic() + OMLX_EVICT_SETTLE_S
    while True:
        result, names = omlx_residency(client, settings)
        stuck = [n for n in names if n in resident]
        if not stuck and result.status is not Status.FAIL:
            return QATResult(
                "gate-evict-omlx", Status.PASS, f"evicted {len(resident)} oMLX model(s)"
            )
        if time.monotonic() >= deadline:
            detail = (
                f"unload accepted but still resident after {OMLX_EVICT_SETTLE_S:.0f}s: {stuck}"
                if stuck
                else f"eviction unconfirmed after {OMLX_EVICT_SETTLE_S:.0f}s (residency unreadable)"
            )
            return QATResult(
                "gate-evict-omlx", Status.FAIL, detail, evidence={"resident": resident}
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
    status = Status.PASS if used_pct < DEFAULT_MEM_CAP_PCT else Status.WARN
    return QATResult(
        "gate-memory", status, f"used {used_pct:.1f}% (cap {DEFAULT_MEM_CAP_PCT:.0f}%)"
    )


def parse_vm_stat(out: str) -> tuple[float, float]:
    """(used_pct, free_gb) from vm_stat text; M-series pages are 16384 B."""
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
    )
    total = sum(pages.get(k, 0) for k in total_keys)
    if total == 0:
        return 99.0, 0.0
    used = sum(pages.get(k, 0) for k in ("Pages active", "Pages wired down"))
    page = 16384
    return used / total * 100.0, pages.get("Pages free", 0) * page / 1024**3


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


def run_gate(
    settings: Settings,
    phase: str,
    transport: httpx.BaseTransport | None = None,
    wait: bool = True,
) -> GateReport:
    """One full inter-phase gate pass; evicts until memory is safe or budget out."""
    checks: list[QATResult] = []
    resident_total = -1
    used_pct = -1.0
    rerun_ids = ("gate-ollama", "gate-omlx", "gate-memory")
    with httpx.Client(transport=transport) as client:
        health = pipeline_health(client, settings)
        checks.append(health)
        if health.status is Status.FAIL:
            return GateReport(phase, tuple(checks), used_pct, resident_total, False, True)
        deadline = time.monotonic() + (WAIT_BUDGET_S if wait else 0.0)
        confirmed_once = False
        while True:
            ol, ol_resident = ollama_residency(client, settings)
            ox, ox_resident = omlx_residency(client, settings)
            mem = vm_memory()
            used_pct = _used_from_detail(mem.detail)
            checks = [c for c in checks if c.scenario_id not in rerun_ids]
            checks.extend([ol, ox, mem])
            resident_total = len(ol_resident) + len(ox_resident)
            if mem.status is Status.PASS and not ol_resident and not ox_resident:
                break
            evicted = False
            if ol_resident:
                checks.append(evict_ollama(client, settings, ol_resident))
                evicted = True
            if ox_resident:
                checks.append(evict_omlx(client, settings, ox_resident))
                evicted = True
            eviction_failures = [
                check
                for check in checks
                if check.scenario_id in ("gate-evict", "gate-evict-omlx")
                and check.status is Status.FAIL
            ]
            if eviction_failures:
                break
            if evicted and not confirmed_once:
                # one confirmation read even with no wait budget, so the report
                # reflects the post-eviction state
                confirmed_once = True
                time.sleep(EVICT_SETTLE_S)
                continue
            if time.monotonic() >= deadline:
                break
            time.sleep(POLL_S)
        checks.append(media_pressure(client))
    blocked = (
        any(c.status is Status.FAIL for c in checks if c.scenario_id == "gate-pipeline")
        or any(
            c.status is Status.FAIL
            for c in checks
            if c.scenario_id in ("gate-ollama", "gate-omlx", "gate-evict", "gate-evict-omlx")
        )
        or (used_pct >= DEFAULT_MEM_CAP_PCT and any(c.scenario_id == "gate-memory" for c in checks))
        or resident_total > 0
    )
    ok = not blocked and all(c.status is Status.PASS for c in checks)
    return GateReport(phase, tuple(checks), used_pct, resident_total, ok, blocked)


def _used_from_detail(detail: str) -> float:
    for token in detail.split():
        if token.endswith("%"):
            try:
                return float(token[:-1])
            except ValueError:
                continue
    return -1.0
