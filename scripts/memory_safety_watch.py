#!/usr/bin/env python3
"""Emergency memory watchdog for multi-model live tests on the host Mac.

Polls swap, memory pressure, and oMLX headroom every two seconds. It trips when
macOS reports critical memory pressure, or when free swap is below the floor
while free memory is also below its floor. Then it stops the test clients
listed in the PID file and unloads idle models while preserving the pinned
Ollama router model.

Low free swap alone is not a trip: macOS grows swap in 1 GiB swapfiles on
demand, so ``vm.swapusage`` free routinely sits under 1 GiB on an idle host
holding stale swapped pages (measured 2026-10-07: 983 MiB free swap, 84% free
memory, pressure level normal). It is dangerous only when memory is also scarce. It also
watches every host-native launchd service from ``config/portal.yaml`` and restarts only
the one whose ``phys_footprint`` stays above its ceiling. ``--services-only`` runs just
that service watch as an always-on launchd job: no swap/pressure trip, no test-client
kills, no model unloads. The script uses only Python's
standard library plus PyYAML for that config, and reuses ``scripts.check_updates._pushover``
for alerts.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")
DEFAULT_LOG = Path.home() / ".portal5" / "logs" / "memory-safety-watch.log"
DEFAULT_ROUTER = "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"
_SWAP_FREE = re.compile(r"free\s*=\s*([0-9.]+)M", re.IGNORECASE)
_MEMORY_FREE = re.compile(r"memory free percentage\s*:\s*([0-9.]+)%", re.IGNORECASE)
#: kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical.
_PRESSURE_CRITICAL = 4
_PHYS_FOOTPRINT = re.compile(r"phys_footprint:\s*([0-9.]+)\s*([KMGT]?B)", re.IGNORECASE)
_FOOTPRINT_SCALE = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


#: A footprint ceiling and whether a measurement backs it; only measured ceilings restart.
@dataclass(frozen=True)
class ServiceCeiling:
    gib: float
    measured: bool


#: Per-service phys_footprint ceilings (GiB), keyed by the fleet entry's `native_service`
#: (or `id`). `eg2-embedding` is measured: 2.09 GiB idle on 2026-10-28, ~5 GB peak at the
#: 2026-10-07 13:29 leak, so 6 GiB restarts. Every other value is provisional and log-only
#: until an operator records measured idle/peak (mlx-transcribe peaked 5.5 GB on 2026-10-07 alone).
DEFAULT_HOST_CEILINGS: dict[str, ServiceCeiling] = {
    "eg2-embedding": ServiceCeiling(6.0, measured=True),
    "vl-retrieval": ServiceCeiling(8.0, measured=False),
    "mlx-speech": ServiceCeiling(8.0, measured=False),
    "mlx-transcribe": ServiceCeiling(6.0, measured=False),
    "mflux": ServiceCeiling(16.0, measured=False),
    "video_mlx": ServiceCeiling(24.0, measured=False),
}
#: Ceiling for a host-native service with no entry above and no config override; provisional.
DEFAULT_HOST_CEILING = ServiceCeiling(4.0, measured=False)
#: Consecutive over-ceiling samples before a breach is reported, and the per-service restart cooldown.
DEFAULT_SERVICE_STRIKES = 3
DEFAULT_RESTART_COOLDOWN_S = 1800.0
#: Always-on services-only sample interval; the debounce still counts samples, not seconds.
DEFAULT_SERVICES_INTERVAL_S = 30.0


def _dotenv_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return default
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("\"'") or default
    return default


def _log(message: str, path: Path) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    line = f"{stamp} {message}"
    print(line, flush=True)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(line + "\n")
    except OSError as exc:
        print(f"{stamp} watchdog log write failed: {exc}", file=sys.stderr, flush=True)


def _command(args: list[str], timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"ERROR: {exc}"


def _snapshot() -> dict[str, Any]:
    swap_text = _command(["sysctl", "vm.swapusage"])
    pressure_text = _command(["memory_pressure", "-Q"])
    level_text = _command(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"])
    swap = _SWAP_FREE.search(swap_text)
    free = _MEMORY_FREE.search(pressure_text)
    level = int(level_text) if level_text.isdigit() else None
    headroom_gib: float | None = None
    omlx_loaded: list[str] = []
    omlx_error = ""
    try:
        url = _dotenv_value("OMLX_URL", "http://localhost:8085").rstrip("/")
        request = urllib.request.Request(f"{url}/v1/models/status", headers=_omlx_headers())
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310 - configured local engine
            data = json.loads(response.read())
        if data.get("final_ceiling") is not None:
            headroom_gib = (
                float(data.get("final_ceiling") or 0) - float(data.get("current_model_memory") or 0)
            ) / 1024**3
        omlx_loaded = [
            str(model.get("id")) for model in data.get("models") or [] if model.get("loaded")
        ]
    except Exception as exc:  # noqa: BLE001 - watchdog must survive a failed telemetry read
        omlx_error = f"{type(exc).__name__}: {exc}"
    return {
        "swap_text": swap_text,
        "swap_free_mb": float(swap.group(1)) if swap else None,
        "pressure_text": pressure_text,
        "memory_free_pct": float(free.group(1)) if free else None,
        "pressure_level": level,
        "pressure_critical": (level is not None and level >= _PRESSURE_CRITICAL)
        or (free is not None and float(free.group(1)) <= 5.0),
        "omlx_headroom_gib": headroom_gib,
        "omlx_loaded": omlx_loaded,
        "omlx_error": omlx_error,
    }


def _omlx_headers() -> dict[str, str]:
    key = _dotenv_value("OMLX_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _read_pids(path: Path) -> list[int]:
    if not path.is_file():
        return []
    result: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 1 and pid != os.getpid() and pid not in result:
            result.append(pid)
    return result


def _kill_test_clients(path: Path, log: Path) -> None:
    pids = _read_pids(path)
    if not pids:
        _log(f"no test-client PIDs found in {path}", log)
        return
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            _log(f"sent SIGTERM to test client pid={pid}", log)
        except ProcessLookupError:
            _log(f"test client pid={pid} already exited", log)
        except OSError as exc:
            _log(f"could not stop test client pid={pid}: {exc}", log)
    time.sleep(1)
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except OSError:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            _log(f"sent SIGKILL to test client pid={pid}", log)
        except OSError as exc:
            _log(f"could not force-stop test client pid={pid}: {exc}", log)


def _request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    opener=None,
    headers: dict[str, str] | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    request_headers = dict(headers or {})
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    client = opener.open if opener is not None else urllib.request.urlopen
    with client(request, timeout=3) as response:  # noqa: S310 - configured local engine
        body = response.read()
        return json.loads(body) if body else {}


def _ollama_base() -> str:
    """Host-side Ollama URL. `.env` is shared with Docker, so its
    host.docker.internal form is rewritten as native-mcp-service.sh does."""
    base = _dotenv_value("WATCH_OLLAMA_URL", _dotenv_value("OLLAMA_URL", "http://localhost:11434"))
    return base.replace("host.docker.internal", "localhost").rstrip("/")


def _unload_ollama(router_model: str, log: Path) -> None:
    base = _ollama_base()
    try:
        result = _request_json(f"{base}/api/ps")
        models = result.get("models") or []
    except Exception as exc:  # noqa: BLE001 - continue to oMLX recovery
        _log(f"Ollama resident query failed: {type(exc).__name__}: {exc}", log)
        return
    for model in models:
        name = str(model.get("name") or model.get("model") or "")
        if not name or name == router_model:
            continue
        try:
            _request_json(
                f"{base}/api/generate",
                {"model": name, "keep_alive": 0, "stream": False},
            )
            _log(f"requested Ollama unload keep_alive=0 model={name}", log)
        except Exception as exc:  # noqa: BLE001 - log and continue through residents
            _log(f"Ollama unload failed model={name}: {type(exc).__name__}: {exc}", log)


def _unload_omlx(log: Path) -> None:
    base = _dotenv_value("OMLX_URL", "http://localhost:8085").rstrip("/")
    key = _dotenv_value("OMLX_API_KEY")
    if not key:
        _log("oMLX admin unload skipped: OMLX_API_KEY is unset", log)
        return
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    try:
        _request_json(f"{base}/admin/api/login", {"api_key": key}, opener=opener)
        status = _request_json(f"{base}/api/status", opener=opener, headers=_omlx_headers())
        active = int(status.get("active_requests") or 0)
        waiting = int(status.get("waiting_requests") or 0)
        if active or waiting:
            _log(f"oMLX unload skipped: active_requests={active} waiting_requests={waiting}", log)
            return
        models_result = _request_json(f"{base}/admin/api/models", opener=opener)
        models = (
            models_result.get("models", models_result)
            if isinstance(models_result, dict)
            else models_result
        )
        for model in models or []:
            if not model.get("loaded") or model.get("pinned") or model.get("is_loading"):
                continue
            model_id = str(model.get("id") or "")
            if not model_id:
                continue
            url = f"{base}/admin/api/models/{urllib.parse.quote(model_id, safe='')}/unload"
            try:
                _request_json(url, {}, opener=opener)
                _log(f"requested idle oMLX unload model={model_id}", log)
            except Exception as exc:  # noqa: BLE001 - oMLX's own enforcer may have won the race
                _log(f"oMLX unload failed model={model_id}: {type(exc).__name__}: {exc}", log)
    except Exception as exc:  # noqa: BLE001 - recovery should continue to notification
        _log(f"oMLX admin unload failed: {type(exc).__name__}: {exc}", log)


def _log_top_processes(log: Path, count: int = 8) -> None:
    """Record the largest resident processes so a trip can be attributed."""
    rows = _command(["ps", "-A", "-o", "rss=,pid=,comm="], timeout=5).splitlines()
    parsed = []
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            parsed.append((int(parts[0]), parts[1], parts[2]))
    for rss_kb, pid, comm in sorted(parsed, reverse=True)[:count]:
        _log(f"top rss {rss_kb / 1024**2:.1f} GiB pid={pid} {comm}", log)


@dataclass(frozen=True)
class HostService:
    key: str
    label: str
    port: int | None


@dataclass
class HostServiceState:
    strikes: dict[str, int] = field(default_factory=dict)
    restarted_at: dict[str, float] = field(default_factory=dict)
    unmeasurable: set[str] = field(default_factory=set)


def _host_native_services(path: Path | None = None) -> list[HostService]:
    """Host-native launchd services from `config/portal.yaml` (fleet entries plus host_jobs)."""
    config_path = path or ROOT / "config" / "portal.yaml"
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    services: list[HostService] = []
    for entry in data.get("mcp_fleet") or []:
        if not isinstance(entry, dict) or not entry.get("host_native"):
            continue
        label = entry.get("launchd_label")
        if not label:
            continue
        services.append(
            HostService(
                str(entry.get("native_service") or entry.get("id") or label),
                str(label),
                entry.get("port"),
            )
        )
    for job in data.get("host_jobs") or []:
        if not isinstance(job, dict) or not job.get("label"):
            continue
        label = str(job["label"])
        services.append(
            HostService(
                str(job.get("service") or label.removeprefix("com.portal5.")),
                label,
                job.get("port"),
            )
        )
    return services


def _service_ceilings(spec: str) -> dict[str, ServiceCeiling]:
    """Defaults overlaid by a `key=gib,...` spec; an override keeps its measured/provisional status."""
    ceilings = dict(DEFAULT_HOST_CEILINGS)
    for item in spec.split(","):
        key, _, value = item.partition("=")
        try:
            gib = float(value)
        except ValueError:
            continue
        ceilings[key.strip()] = ServiceCeiling(
            gib, ceilings.get(key.strip(), DEFAULT_HOST_CEILING).measured
        )
    return ceilings


def _service_pid(label: str) -> int | None:
    text = _command(["launchctl", "print", f"gui/{os.getuid()}/{label}"], timeout=3)
    match = re.search(r"^\s*pid = (\d+)\s*$", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _python_pid(pid: int) -> int | None:
    """The pid itself or its first python descendant: launchd jobs exec, shell wrappers do not."""
    rows = _command(["ps", "-A", "-o", "pid=,ppid=,comm="], timeout=5).splitlines()
    comm: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        comm[int(parts[0])] = parts[2]
        children.setdefault(int(parts[1]), []).append(int(parts[0]))
    queue, seen = [pid], set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        executable = comm.get(current, "").split(" ", 1)[0]
        if Path(executable).name.lower().startswith("python"):
            return current
        queue.extend(children.get(current, []))
    return None


def _footprint_bytes(pid: int) -> int | None:
    """phys_footprint from `footprint -p`, in bytes; None when the output is unparseable."""
    text = _command(["footprint", "-p", str(pid)], timeout=15)
    match = _PHYS_FOOTPRINT.search(text)
    if not match:
        return None
    return int(float(match.group(1)) * _FOOTPRINT_SCALE[match.group(2).upper()])


def _restart_service(label: str, log: Path) -> None:
    output = _command(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], timeout=10)
    _log(f"restart host service label={label}: {output or 'ok'}", log)


def check_host_services(
    state: HostServiceState,
    log: Path,
    *,
    services: list[HostService] | None = None,
    ceilings: dict[str, ServiceCeiling] | None = None,
    strikes: int = DEFAULT_SERVICE_STRIKES,
    cooldown_s: float = DEFAULT_RESTART_COOLDOWN_S,
    config_path: Path | None = None,
    now: float | None = None,
) -> list[HostService]:
    """Report host services held over their ceiling, restarting only measured ones."""
    resolved = dict(DEFAULT_HOST_CEILINGS if ceilings is None else ceilings)
    candidates = _host_native_services(config_path) if services is None else services
    clock = time.monotonic() if now is None else now
    restarted: list[HostService] = []
    for service in candidates:
        ceiling = resolved.get(service.key, DEFAULT_HOST_CEILING)
        limit = ceiling.gib * 1024**3
        status = "measured" if ceiling.measured else "provisional"
        pid = _service_pid(service.label)
        python_pid = _python_pid(pid) if pid else None
        footprint = _footprint_bytes(python_pid) if python_pid else None
        if footprint is None:
            state.strikes[service.key] = 0
            if service.key not in state.unmeasurable:
                state.unmeasurable.add(service.key)
                _log(
                    f"host service unmeasurable, never restarted: service={service.key} "
                    f"label={service.label} pid={pid}",
                    log,
                )
            continue
        state.unmeasurable.discard(service.key)
        if footprint <= limit:
            state.strikes[service.key] = 0
            continue
        count = state.strikes.get(service.key, 0) + 1
        state.strikes[service.key] = count
        summary = (
            f"service={service.key} label={service.label} pid={python_pid} "
            f"footprint={footprint / 1024**3:.2f} GiB ceiling={limit / 1024**3:.2f} GiB "
            f"ceiling_status={status}"
        )
        if count < strikes:
            _log(f"host service over ceiling: {summary} sample={count}/{strikes}", log)
            continue
        if not ceiling.measured:
            if count == strikes:
                _log(f"HOST SERVICE CEILING BREACH (log-only): {summary} samples={count}", log)
            continue
        last = state.restarted_at.get(service.key)
        if last is not None and clock - last < cooldown_s:
            continue
        _log(f"HOST SERVICE CEILING BREACH (restart): {summary} samples={count}", log)
        _restart_service(service.label, log)
        state.restarted_at[service.key] = clock
        state.strikes[service.key] = 0
        restarted.append(service)
    return restarted


def _trip(snapshot: dict[str, Any], floor_mb: float, memory_floor_pct: float) -> str | None:
    if snapshot.get("pressure_critical"):
        return (
            f"memory pressure is critical (level={snapshot.get('pressure_level')}, "
            f"{snapshot.get('pressure_text', 'unknown')})"
        )
    swap = snapshot.get("swap_free_mb")
    free = snapshot.get("memory_free_pct")
    if swap is not None and swap < floor_mb and free is not None and free < memory_floor_pct:
        return (
            f"swap free {swap:.1f} MiB is below {floor_mb:.0f} MiB and memory free "
            f"{free:.0f}% is below {memory_floor_pct:.0f}%"
        )
    return None


def watch(
    *,
    pid_file: Path = DEFAULT_PID_FILE,
    log: Path = DEFAULT_LOG,
    interval_s: float = 2.0,
    swap_floor_mb: float = 1024.0,
    memory_floor_pct: float = 20.0,
    service_ceilings: dict[str, ServiceCeiling] | None = None,
    restart_cooldown_s: float = DEFAULT_RESTART_COOLDOWN_S,
    once: bool = False,
) -> int:
    router_model = _dotenv_value("LLM_ROUTER_MODEL", DEFAULT_ROUTER)
    host_services = _host_native_services()
    service_state = HostServiceState()
    while True:
        snapshot = _snapshot()
        summary = (
            f"swap_free_mb={snapshot['swap_free_mb']} "
            f"memory_free_pct={snapshot['memory_free_pct']} "
            f"pressure_level={snapshot['pressure_level']} "
            f"omlx_headroom_gib={snapshot['omlx_headroom_gib']} "
            f"omlx_loaded={snapshot['omlx_loaded']}"
        )
        if snapshot["omlx_error"]:
            summary += f" omlx_error={snapshot['omlx_error']}"
        _log(summary, log)
        check_host_services(
            service_state,
            log,
            services=host_services,
            ceilings=service_ceilings,
            cooldown_s=restart_cooldown_s,
        )
        reason = _trip(snapshot, swap_floor_mb, memory_floor_pct)
        if reason:
            _log(f"MEMORY SAFETY TRIP: {reason}", log)
            _log_top_processes(log)
            _kill_test_clients(pid_file, log)
            _unload_ollama(router_model, log)
            _unload_omlx(log)
            try:
                from check_updates import _pushover

                _pushover("Portal host-memory safety trip", reason, high=True)
            except Exception as exc:  # noqa: BLE001 - local alert must not mask recovery
                _log(f"Pushover notification failed: {type(exc).__name__}: {exc}", log)
            return 2
        if once:
            return 0
        time.sleep(max(0.1, interval_s))


def watch_services(
    *,
    log: Path = DEFAULT_LOG,
    interval_s: float = DEFAULT_SERVICES_INTERVAL_S,
    service_ceilings: dict[str, ServiceCeiling] | None = None,
    restart_cooldown_s: float = DEFAULT_RESTART_COOLDOWN_S,
    services: list[HostService] | None = None,
    once: bool = False,
) -> int:
    """Always-on mode: host-service footprint ceilings only — no trip, kills or unloads."""
    host_services = _host_native_services() if services is None else services
    state = HostServiceState()
    while True:
        restarted = check_host_services(
            state,
            log,
            services=host_services,
            ceilings=service_ceilings,
            cooldown_s=restart_cooldown_s,
        )
        _log(
            f"host service sample: services={len(host_services)} "
            f"restarted={[service.key for service in restarted]}",
            log,
        )
        if once:
            return 0
        time.sleep(max(0.1, interval_s))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="seconds between samples (default: 2, or 30 with --services-only)",
    )
    parser.add_argument(
        "--swap-floor-mb",
        type=float,
        default=float(_dotenv_value("WATCH_SWAP_FLOOR_MB", "1024")),
    )
    parser.add_argument(
        "--memory-floor-pct",
        type=float,
        default=20.0,
        help="low swap trips only while memory free is below this percentage",
    )
    parser.add_argument(
        "--services-only",
        action="store_true",
        help=(
            "always-on host-service footprint ceilings only: no swap/pressure trip, "
            "no test-client kills, no model unloads"
        ),
    )
    parser.add_argument("--once", action="store_true", help="record one sample and exit")
    parser.add_argument(
        "--service-ceilings",
        default=_dotenv_value("WATCH_HOST_CEILINGS_GIB", ""),
        help=(
            "per-service footprint ceilings in GiB, e.g. eg2-embedding=0.5,mflux=16 "
            "(a provisional ceiling logs only; overriding it does not make it restart-eligible)"
        ),
    )
    parser.add_argument(
        "--restart-cooldown-s",
        type=float,
        default=float(_dotenv_value("WATCH_HOST_RESTART_COOLDOWN_S", "1800")),
        help="minimum seconds between host-service restarts",
    )
    args = parser.parse_args(argv)
    interval_s = args.interval
    if interval_s is None:
        interval_s = DEFAULT_SERVICES_INTERVAL_S if args.services_only else 2.0
    ceilings = _service_ceilings(args.service_ceilings)
    if args.services_only:
        return watch_services(
            log=args.log,
            interval_s=interval_s,
            service_ceilings=ceilings,
            restart_cooldown_s=args.restart_cooldown_s,
            once=args.once,
        )
    return watch(
        pid_file=args.pid_file,
        log=args.log,
        interval_s=interval_s,
        swap_floor_mb=args.swap_floor_mb,
        memory_floor_pct=args.memory_floor_pct,
        service_ceilings=ceilings,
        restart_cooldown_s=args.restart_cooldown_s,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
