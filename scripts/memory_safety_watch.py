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
memory, pressure level normal). It is dangerous only when memory is also scarce. The script uses only Python's standard library
and reuses ``scripts.check_updates._pushover`` for alerts.
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")
DEFAULT_LOG = Path.home() / ".portal5" / "logs" / "memory-safety-watch.log"
DEFAULT_ROUTER = "hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M-ctx2k"
_SWAP_FREE = re.compile(r"free\s*=\s*([0-9.]+)M", re.IGNORECASE)
_MEMORY_FREE = re.compile(r"memory free percentage\s*:\s*([0-9.]+)%", re.IGNORECASE)
#: kern.memorystatus_vm_pressure_level: 1 normal, 2 warning, 4 critical.
_PRESSURE_CRITICAL = 4


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
    once: bool = False,
) -> int:
    router_model = _dotenv_value("LLM_ROUTER_MODEL", DEFAULT_ROUTER)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--interval", type=float, default=2.0)
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
    parser.add_argument("--once", action="store_true", help="record one sample and exit")
    args = parser.parse_args(argv)
    return watch(
        pid_file=args.pid_file,
        log=args.log,
        interval_s=args.interval,
        swap_floor_mb=args.swap_floor_mb,
        memory_floor_pct=args.memory_floor_pct,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
