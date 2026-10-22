"""Shared host-quiet preflight and snapshots for live UAT entry points."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PID_FILE = Path("/tmp/portal5-memory-safety-test-pids")
ORCHESTRATE_ROOT = Path.home() / ".claude" / "orchestrate"
DEFAULT_MIN_HEADROOM_GIB = 1.5
_ACTIVE_STATUSES = {"active", "in_progress", "in-progress", "pending", "queued", "running"}


def _env_value(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'") or default
    return default


def _json_request(
    url: str, *, method: str = "GET", api_key: str = "", payload: dict[str, Any] | None = None
) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310 - local services only
        body = response.read()
    return json.loads(body) if body else {}


def _process_lines() -> tuple[list[str], str | None]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"process table unavailable ({type(exc).__name__})"
    if result.returncode:
        return [], "ps failed"
    return result.stdout.splitlines(), None


def _process_kind(command: str) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    basenames = [Path(part).name.lower() for part in parts]
    lowered = " ".join(parts).lower()
    if "dispatch.py" in basenames:
        return "dispatch lane job"
    if any(name in {"pytest", "py.test"} for name in basenames) or "xdist" in basenames:
        return "pytest/xdist"
    if any(name in {"run_arm.py", "wfe_sweep_unattended.sh"} for name in basenames):
        return "WFE/bench run"
    if "tests.wfe.campaign" in lowered or "tests/wfe/campaign.py" in lowered:
        return "WFE/bench run"
    if any(name.startswith("bench_") and name.endswith(".py") for name in basenames):
        return "WFE/bench run"
    return None


def _process_summary(command: str, kind: str) -> str:
    if kind == "dispatch lane job":
        return "dispatch.py"
    if kind == "pytest/xdist":
        return "pytest/xdist worker"
    match = re.search(
        r"(?:tests[./]wfe[./][\w.-]+|wfe_sweep_unattended\.sh|[\w./-]*bench[\w.-]*\.py)",
        command,
        re.I,
    )
    return match.group(0) if match else kind


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _process_row(line: str) -> tuple[int, int | None, str] | None:
    try:
        raw_pid, raw_ppid, command = line.strip().split(maxsplit=2)
        return int(raw_pid), int(raw_ppid), command
    except (ValueError, TypeError):
        return None


def _ancestor_pids(lines: list[str], own_pid: int) -> set[int]:
    parents = {
        pid: ppid
        for line in lines
        if (row := _process_row(line)) is not None
        for pid, ppid, _command in [row]
        if ppid is not None
    }
    found = set()
    while own_pid in parents and parents[own_pid] not in found:
        own_pid = parents[own_pid]
        found.add(own_pid)
    return found


def _scan_processes(
    lines: list[str], own_pid: int | None = None, ignore_pids: set[int] | None = None
) -> list[dict[str, Any]]:
    own_pid = os.getpid() if own_pid is None else own_pid
    ignored = ignore_pids or set()
    found = []
    for line in lines:
        row = _process_row(line)
        if row is None:
            continue
        pid, _ppid, command = row
        kind = _process_kind(command)
        if kind and pid != own_pid and pid not in ignored:
            found.append({"pid": pid, "kind": kind, "process": _process_summary(command, kind)})
    return found


def _pid_file_processes(
    path: Path = MEMORY_PID_FILE, ignore_pids: set[int] | None = None
) -> list[dict[str, Any]]:
    ignored = ignore_pids or set()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [
            {
                "pid": None,
                "kind": "WFE/bench PID file",
                "process": f"unreadable ({type(exc).__name__})",
            }
        ]
    found = []
    for line in lines:
        value = line.strip()
        if not value:
            continue
        try:
            pid = int(value)
        except ValueError:
            return [{"pid": None, "kind": "WFE/bench PID file", "process": "malformed PID record"}]
        if pid <= 1:
            return [{"pid": pid, "kind": "WFE/bench PID file", "process": "invalid PID record"}]
        if pid not in ignored and _pid_alive(pid):
            found.append({"pid": pid, "kind": "WFE/bench run", "process": "memory-safety PID file"})
    return found


def _registry_processes(
    root: Path = ORCHESTRATE_ROOT, ignore_pids: set[int] | None = None
) -> list[dict[str, Any]]:
    ignored = ignore_pids or set()
    found: list[dict[str, Any]] = []
    registry = root / "registry.json"
    if registry.exists():
        try:
            data = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            found.append(
                {"pid": None, "kind": "dispatch lane job", "process": "registry unreadable"}
            )
        else:
            if _has_active_status(data):
                found.append(
                    {
                        "pid": None,
                        "kind": "dispatch lane job",
                        "process": "active orchestrate registry entry",
                    }
                )
    locks = root / "locks"
    if locks.is_dir():
        for path in locks.glob("*.lock"):
            try:
                value = path.read_text(encoding="utf-8").strip()
                pid = int(value)
            except (OSError, ValueError):
                found.append(
                    {
                        "pid": None,
                        "kind": "dispatch lane job",
                        "process": "unverifiable orchestrate lock",
                    }
                )
                continue
            if pid > 1 and pid not in ignored and _pid_alive(pid):
                found.append(
                    {"pid": pid, "kind": "dispatch lane job", "process": "active orchestrate lock"}
                )
    return found


def _has_active_status(value: Any) -> bool:
    if isinstance(value, dict):
        if str(value.get("status", "")).lower() in _ACTIVE_STATUSES:
            return True
        return any(_has_active_status(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_active_status(item) for item in value)
    return False


def _vm_stat_free_gib() -> tuple[float | None, str | None]:
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if result.returncode:
        return None, "vm_stat failed"
    page_size = re.search(r"page size of (\d+) bytes", result.stdout, re.I)
    size = int(page_size.group(1)) if page_size else 16384
    pages = {}
    for label in ("Pages free", "Pages inactive"):
        match = re.search(rf"{re.escape(label)}:\s*(\d+)", result.stdout)
        if match:
            pages[label] = int(match.group(1))
    if len(pages) != 2:
        return None, "vm_stat did not report free and inactive pages"
    return round(sum(pages.values()) * size / 1024**3, 2), None


def _resident_models(data: Any) -> list[dict[str, Any]]:
    models = data.get("models", []) if isinstance(data, dict) else []
    found = []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        if model.get("loaded") is False:
            continue
        name = model.get("name") or model.get("model") or model.get("id")
        if name:
            resident = {"name": str(name)}
            for key in ("size", "size_vram", "actual_size", "current_model_memory"):
                if model.get(key) is not None:
                    resident[f"{key}_gib"] = round(float(model[key]) / 1024**3, 2)
            found.append(resident)
    return found


def capture_snapshot(pipeline_url: str, api_key: str) -> dict[str, Any]:
    """Capture current host memory, residents and competing heavy processes."""
    raw_lines, process_error = _process_lines()
    own_pid = os.getpid()
    ancestors = _ancestor_pids(raw_lines, own_pid)
    heavy = _scan_processes(raw_lines, own_pid, ancestors)
    heavy.extend(_pid_file_processes(ignore_pids=ancestors))
    heavy.extend(_registry_processes(ignore_pids=ancestors))

    free_gib, vm_error = _vm_stat_free_gib()
    base = pipeline_url.rstrip("/")
    load_plan = None
    load_plan_error = None
    try:
        load_plan = _json_request(
            f"{base}/admin/load-plan",
            method="POST",
            api_key=api_key,
            payload={"models": []},
        )
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        load_plan_error = f"{type(exc).__name__}: {exc}"

    ollama_base = _env_value("WATCH_OLLAMA_URL", _env_value("OLLAMA_URL", "http://localhost:11434"))
    ollama_base = ollama_base.replace("host.docker.internal", "localhost").rstrip("/")
    try:
        ollama = _json_request(f"{ollama_base}/api/ps")
        ollama_residents = _resident_models(ollama)
        ollama_error = None
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        ollama_residents = []
        ollama_error = f"{type(exc).__name__}: {exc}"

    omlx_base = _env_value("OMLX_URL", "http://localhost:8085").rstrip("/")
    try:
        omlx_status = _json_request(
            f"{omlx_base}/v1/models/status", api_key=_env_value("OMLX_API_KEY")
        )
        omlx_residents = _resident_models(omlx_status)
        omlx_error = None
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        omlx_status = {}
        omlx_residents = []
        omlx_error = f"{type(exc).__name__}: {exc}"

    plan_headroom = _number(load_plan, "available_gib")
    plan_source = "Pipeline /admin/load-plan available_gib" if plan_headroom is not None else None
    if plan_headroom is None:
        plan_headroom = _number(load_plan, "headroom_gib")
        if plan_headroom is not None:
            plan_source = "Pipeline /admin/load-plan headroom_gib"
    headroom = plan_headroom if plan_headroom is not None else free_gib
    source = plan_source or ("vm_stat free + inactive" if free_gib is not None else None)
    busy_requests = int(load_plan.get("busy_requests") or 0) if isinstance(load_plan, dict) else 0
    return {
        "sampled_at": datetime.now(UTC).isoformat(),
        "free_memory_gib": free_gib,
        "vm_stat_error": vm_error,
        "headroom_gib": headroom,
        "headroom_source": source,
        "minimum_headroom_gib": _minimum_headroom_gib(),
        "pipeline_load_plan": load_plan,
        "pipeline_load_plan_error": load_plan_error,
        "ollama_residents": ollama_residents,
        "ollama_error": ollama_error,
        "omlx_residents": omlx_residents,
        "omlx_error": omlx_error,
        "busy_requests": busy_requests,
        "other_heavy_processes": heavy,
        "process_scan_error": process_error,
    }


def _number(value: Any, key: str) -> float | None:
    try:
        number = (
            float(value[key]) if isinstance(value, dict) and value.get(key) is not None else None
        )
    except (TypeError, ValueError):
        return None
    return number


def _minimum_headroom_gib() -> float:
    try:
        return max(
            0.0, float(os.environ.get("UAT_MIN_HOST_HEADROOM_GIB", DEFAULT_MIN_HEADROOM_GIB))
        )
    except ValueError:
        return DEFAULT_MIN_HEADROOM_GIB


def blockers(snapshot: dict[str, Any]) -> list[str]:
    """Return reasons the host is not ready for a live measurement run."""
    reasons = []
    if snapshot.get("process_scan_error"):
        reasons.append(snapshot["process_scan_error"])
    for process in snapshot.get("other_heavy_processes", []):
        pid = process.get("pid")
        suffix = f" (pid {pid})" if pid else ""
        reasons.append(f"{process['kind']} is running{suffix}: {process['process']}")
    if snapshot.get("busy_requests"):
        reasons.append(f"Pipeline reports {snapshot['busy_requests']} active request(s)")
    headroom = snapshot.get("headroom_gib")
    minimum = snapshot.get("minimum_headroom_gib", DEFAULT_MIN_HEADROOM_GIB)
    if headroom is None:
        reasons.append("host memory headroom is unavailable")
    elif headroom < minimum:
        reasons.append(f"host memory headroom {headroom:.1f} GiB is below {minimum:.1f} GiB")
    return reasons


def begin_run(pipeline_url: str, api_key: str, *, force: bool = False) -> dict[str, Any]:
    """Capture and evaluate the start state, recording any forced override."""
    start = capture_snapshot(pipeline_url, api_key)
    reasons = blockers(start)
    override = None
    if force:
        override = (
            "operator supplied --force; overridden blockers: " + "; ".join(reasons)
            if reasons
            else "operator supplied --force; no blockers were observed"
        )
    return {
        "allowed": not reasons or force,
        "force_requested": force,
        "override_reason": override,
        "blockers": reasons,
        "start": start,
    }


def finish_run(context: dict[str, Any], pipeline_url: str, api_key: str) -> None:
    """Attach the end-of-run host snapshot."""
    context["end"] = capture_snapshot(pipeline_url, api_key)


def refusal(context: dict[str, Any]) -> str:
    return "refusing to start: " + "; ".join(context.get("blockers", []))
