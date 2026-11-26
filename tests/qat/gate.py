"""Inter-phase gate: pipeline health, engine health + residency-aware
eviction, host memory guard, MLX media pressure report.

Eviction is residency-checked: oMLX 0.8.1 returns HTTP 400 for an unload of
an already-cold model, so residency is read from /v1/models/status (falling
back to /v1/models/loaded) and only resident models are unloaded. The unload
itself is asynchronous (HTTP 202): the gate polls residency for
OMLX_EVICT_SETTLE_S before reporting PASS, since Metal memory is reclaimed
over the next seconds. Ollama keep_alive 0 is asynchronous too: /api/ps is
polled for OLLAMA_EVICT_BUDGET_S while a request is in flight or a runner is
still releasing. The retained MLX media services (mlx-speech :8918,
mflux :8933, video-mlx :8935) are memory-pressure reporters only — never killed.
"""

from __future__ import annotations

import fcntl
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
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
#: Short /api/generate → loaded-runners drop, ollama.log n=78: p50 12.6s, p95 42.2s, max 50.2s.
OLLAMA_EVICT_BUDGET_S = 60.0
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
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
    detail = "; ".join(errors) or "no readable residency endpoint"
    return QATResult(
        "gate-omlx", Status.FAIL, f"oMLX residency endpoints unreachable: {detail}"
    ), []


def evict_ollama(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    """Unload residents and poll /api/ps through in-flight work, a release, or the budget."""
    started = time.monotonic()
    deadline = started + OLLAMA_EVICT_BUDGET_S
    blocked = _request_ollama_unload(client, settings, resident, deadline)
    if isinstance(blocked, QATResult):
        return blocked
    return _wait_ollama_unloaded(client, settings, resident, started, deadline, blocked)


def _request_ollama_unload(
    client: httpx.Client, settings: Settings, resident: list[str], deadline: float
) -> QATResult | set[str]:
    """POST keep_alive 0. A timeout means the request is queued behind in-flight work."""
    blocked: set[str] = set()
    attempted = False
    for name in resident:
        if attempted and time.monotonic() >= deadline:
            blocked.add(name)
            continue
        attempted = True
        try:
            response = client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": name, "keep_alive": 0},
                timeout=min(15.0, max(deadline - time.monotonic(), 0.01)),
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
    deadline: float,
    blocked: set[str],
) -> QATResult:
    seen: set[str] = set()
    if blocked:
        seen.add("in_flight")
    last_state: dict[str, str] = dict.fromkeys(blocked, "in_flight")
    last_expiry: dict[str, str] = {}
    previous_expiry: dict[str, datetime] = {}
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
        if time.monotonic() >= deadline:
            return _ollama_evict_stuck(models, last_state, last_expiry, time.monotonic() - started)
        _poll_pause(min(OLLAMA_EVICT_POLL_S, max(0.0, deadline - time.monotonic())))


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
    if not name:
        return False
    from portal.platform.inference.load_guard import LoadGuard

    path = LoadGuard._activity_path("ollama", name)
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
            "budget_s": OLLAMA_EVICT_BUDGET_S,
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
            f"Ollama models remain resident after {elapsed:.1f}s/"
            f"{OLLAMA_EVICT_BUDGET_S:.0f}s ({summary}): {names}"
        ),
        evidence={
            "resident": names,
            "state": dict(last_state),
            "expires_at": dict(last_expiry),
            "waited_s": round(elapsed, 3),
            "budget_s": OLLAMA_EVICT_BUDGET_S,
        },
    )


def _poll_pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def evict_omlx(client: httpx.Client, settings: Settings, resident: list[str]) -> QATResult:
    """Unload residency-confirmed models through the oMLX admin API, then wait out
    oMLX 0.8.1's async unload (200/202/204): PASS only once residency confirms the
    models are no longer loaded, not at the moment the unload is accepted."""
    already_cold: list[str] = []
    for name in resident:
        encoded = quote(name, safe=":")
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
            if r.status_code == 404:
                residency, names = omlx_residency(client, settings)
                reason = r.text.strip() or "empty response body"
                if residency.status is Status.FAIL:
                    return QATResult(
                        "gate-evict-omlx",
                        Status.FAIL,
                        f"unload {name}: HTTP 404 ({reason}); residency check failed: {residency.detail}",
                    )
                if name in names:
                    return QATResult(
                        "gate-evict-omlx",
                        Status.FAIL,
                        f"unload {name}: HTTP 404 ({reason}); model is still resident",
                    )
                already_cold.append(name)
                continue
            if r.status_code not in (200, 202, 204, 400):
                reason = r.text.strip()
                return QATResult(
                    "gate-evict-omlx",
                    Status.FAIL,
                    f"unload {name}: HTTP {r.status_code}" + (f" ({reason})" if reason else ""),
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
            detail = f"evicted {len(resident)} oMLX model(s)"
            if already_cold:
                detail += f"; 404 confirmed cold: {', '.join(already_cold)}"
            return QATResult("gate-evict-omlx", Status.PASS, detail)
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
            if not ol_resident and not ox_resident:
                # clean when memory is under the cap; otherwise nothing is
                # evictable and waiting out the budget cannot help (F9)
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
