"""Section 1 — every repo launchd job's installed plist, program, and process state."""

from __future__ import annotations

import os
import plistlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import run_cmd
from .model import Hop, Status, short

_ENGINE_HINTS = ("omlx", "ollama")
_DEFAULT_INSTALL_DIR = Path.home() / "Library" / "LaunchAgents"
_SYSTEM_INSTALL_DIR = Path("/Library/LaunchDaemons")
_STANDARD_PRIORITY = 20
# Root actions go through this dispatcher when it is installed: it is NOPASSWD in
# sudoers, so a hint stays runnable without a password prompt.
_ROOT_DISPATCHER = Path(os.environ.get("PORTAL5_ROOT_DISPATCHER", "/usr/local/sbin/portal5-root"))
# label -> (dispatcher action, fallback command)
_REPAIRS: dict[str, tuple[str, str]] = {
    "com.portal5.powermetrics": ("install-powermetrics", "sudo ./launch.sh install-powermetrics"),
    "com.portal5.omlx": ("", "./launch.sh install-omlx"),
}

_RUNNING = re.compile(r"^\s*state = running\b", re.M)
_PID = re.compile(r"^\s*pid = (\d+)", re.M)
_RUNS = re.compile(r"^\s*runs = (\d+)", re.M)
_LAST_EXIT = re.compile(r"^\s*last exit code = (-?\d+)", re.M)
_INTERVAL = re.compile(r"^\s*run interval = (\d+) seconds", re.M)
_ARGUMENTS = re.compile(r"^\s*arguments = \{\n(.*?)^\s*\}$", re.M | re.S)


@dataclass(frozen=True)
class JobState:
    """What launchd reports for one label: loaded, resident, and its run history."""

    loaded: bool
    running: bool = False
    pid: int | None = None
    runs: int | None = None
    last_exit: int | None = None
    interval_s: int | None = None
    arguments: tuple[str, ...] = ()


def parse_plist(data: bytes) -> dict[str, Any]:
    """Decode a plist file into its top-level dict (empty when it is not a dict)."""
    loaded = plistlib.loads(data)
    return loaded if isinstance(loaded, dict) else {}


def process_type(cfg: dict[str, Any]) -> str:
    value = cfg.get("ProcessType")
    return str(value) if value else "Standard"


def env_keys(cfg: dict[str, Any]) -> list[str]:
    env = cfg.get("EnvironmentVariables")
    return sorted(env) if isinstance(env, dict) else []


def schedule(cfg: dict[str, Any]) -> str:
    """``resident`` (KeepAlive), ``periodic`` (an interval/calendar job), or ``oneshot``."""
    if cfg.get("KeepAlive"):
        return "resident"
    if cfg.get("StartInterval") or cfg.get("StartCalendarInterval"):
        return "periodic"
    return "oneshot"


def is_daemon(cfg: dict[str, Any]) -> bool:
    """A job that declares a ``UserName`` installs as a root LaunchDaemon, not a user agent."""
    return bool(cfg.get("UserName"))


def install_dir(cfg: dict[str, Any]) -> Path:
    return _SYSTEM_INSTALL_DIR if is_daemon(cfg) else _DEFAULT_INSTALL_DIR


def is_engine(label: str) -> bool:
    return any(hint in label.lower() for hint in _ENGINE_HINTS)


def program_args(cfg: dict[str, Any]) -> list[str]:
    args = cfg.get("ProgramArguments")
    if isinstance(args, list) and args:
        return [str(arg) for arg in args]
    program = cfg.get("Program")
    return [str(program)] if program else []


def program_paths(cfg: dict[str, Any]) -> list[str]:
    """Absolute paths the job would execute (an interpreter, then its script or binary)."""
    return [arg for arg in program_args(cfg) if arg.startswith("/")]


def missing_program_paths(cfg: dict[str, Any]) -> list[str]:
    return [path for path in program_paths(cfg) if not Path(path).exists()]


def templated(cfg: dict[str, Any]) -> bool:
    """Installers substitute ``__PLACEHOLDER__`` tokens; such a plist cannot be compared."""
    return bool(unsubstituted(cfg))


def unsubstituted(cfg: dict[str, Any]) -> list[str]:
    """Placeholder tokens still present in the job's arguments (an unsubstituted install)."""
    return sorted(
        {token for arg in program_args(cfg) for token in re.findall(r"__[A-Z0-9_]+__", arg)}
    )


def repair_hint(label: str) -> str:
    """The command that reinstalls this job, through the passwordless dispatcher if present."""
    action, fallback = _REPAIRS.get(label, ("", "re-run the installer"))
    if action and _ROOT_DISPATCHER.is_file():
        return f"sudo -n {_ROOT_DISPATCHER} {action}"
    return fallback


def parse_priority(output: str) -> int | None:
    """First integer line of ``ps -o pri= -p <pid>``."""
    for line in output.splitlines():
        text = line.strip()
        if text.isdigit():
            return int(text)
    return None


def parse_arguments(text: str) -> tuple[str, ...]:
    """The resolved ``arguments = { … }`` block launchd holds for the loaded job."""
    match = _ARGUMENTS.search(text)
    if not match:
        return ()
    return tuple(line.strip() for line in match.group(1).splitlines() if line.strip())


def parse_job_state(text: str, loaded: bool) -> JobState:
    """Read ``launchctl print <domain>/<label>`` into the facts a verdict needs."""

    def number(pattern: re.Pattern[str]) -> int | None:
        match = pattern.search(text)
        return int(match.group(1)) if match else None

    return JobState(
        loaded=loaded,
        running=bool(_RUNNING.search(text)),
        pid=number(_PID),
        runs=number(_RUNS),
        last_exit=number(_LAST_EXIT),
        interval_s=number(_INTERVAL),
        arguments=parse_arguments(text),
    )


def query_job(label: str, daemon: bool) -> JobState:
    domain = "system" if daemon else f"gui/{os.getuid()}"
    result = run_cmd(["launchctl", "print", f"{domain}/{label}"], timeout=10)
    return parse_job_state(result.stdout, result.ok)


def priority_hop(label: str, priority: int) -> Hop:
    """Engines are never de-prioritised; nothing in the fleet should sit at Background."""
    engine = is_engine(label)
    expected = "pri>=20 (engines are never Background)"
    if priority >= _STANDARD_PRIORITY:
        return Hop(label, Status.PASS, f"pri={priority}", expected, "engine" if engine else "")
    if priority <= 4 or engine:
        return Hop(label, Status.FAIL, f"pri={priority}", expected, "de-prioritised")
    return Hop(label, Status.WARN, f"pri={priority}", expected)


def load_installed(label: str, directory: Path) -> dict[str, Any] | None:
    path = directory / f"{label}.plist"
    if not path.is_file():
        return None
    try:
        return parse_plist(path.read_bytes())
    except Exception:  # noqa: BLE001 - an unreadable plist is reported by installed_hop's caller
        return {}


def installed_hop(
    label: str,
    repo_cfg: dict[str, Any],
    installed: dict[str, Any] | None,
    loaded: tuple[str, ...] = (),
) -> list[Hop]:
    """The installed plist exists, matches ProcessType, carries the env keys, and can execute."""
    directory = install_dir(repo_cfg)
    if installed is None:
        return [
            Hop(
                f"plist {label}",
                Status.FAIL,
                f"installed=missing ({directory})",
                "installed plist present",
            )
        ]
    hops = [
        Hop(
            f"plist {label}",
            Status.PASS if process_type(installed) == process_type(repo_cfg) else Status.FAIL,
            f"ProcessType={process_type(installed)}",
            process_type(repo_cfg),
        )
    ]
    missing = [key for key in env_keys(repo_cfg) if key not in env_keys(installed)]
    hops.append(
        Hop(
            f"env {label}",
            Status.FAIL if missing else Status.PASS,
            f"keys={len(env_keys(installed))}",
            ",".join(env_keys(repo_cfg)) or "none",
            f"missing={','.join(missing)}" if missing else "",
        )
    )
    hops.append(program_hop(label, installed, loaded))
    if not templated(repo_cfg) and program_args(repo_cfg) != program_args(installed):
        hops.append(
            Hop(
                f"args {label}",
                Status.WARN,
                " ".join(program_args(installed)) or "none",
                " ".join(program_args(repo_cfg)) or "none",
                f"installed plist differs from the repo copy; {repair_hint(label)}",
            )
        )
    return hops


def program_hop(label: str, installed: dict[str, Any], loaded: tuple[str, ...] = ()) -> Hop:
    """Every absolute program path exists and no installer placeholder survives."""
    tokens = unsubstituted(installed)
    if tokens:
        runs = f"loaded={short(' '.join(loaded), 60)}" if loaded else "loaded=none"
        return Hop(
            f"program {label}",
            Status.WARN,
            f"unsubstituted={','.join(tokens)}",
            "rendered with the documented substitutions",
            f"{runs}; {repair_hint(label)}",
        )
    missing = missing_program_paths(installed)
    paths = program_paths(installed)
    return Hop(
        f"program {label}",
        Status.FAIL if missing or not paths else Status.PASS,
        f"missing={missing[0]}" if missing else f"paths={len(paths)}",
        "every absolute program path exists",
    )


def process_hop(label: str, cfg: dict[str, Any], state: JobState) -> Hop:
    """Resident jobs must be running at priority; periodic ones must have a healthy last run."""
    expected_purpose = schedule(cfg)
    if not state.loaded:
        return Hop(f"process {label}", Status.FAIL, "not loaded", "launchctl knows the job")
    if expected_purpose == "resident":
        if state.pid is None:
            detail = f"runs={state.runs} last exit={state.last_exit}"
            return Hop(f"process {label}", Status.FAIL, "pid=none (KeepAlive)", "running", detail)
        ps = run_cmd(["ps", "-o", "pri=", "-p", str(state.pid)], timeout=10)
        priority = parse_priority(ps.stdout)
        if priority is None:
            return Hop(
                f"process {label}", Status.FAIL, f"pid={state.pid} pri=unreadable", "pri>=20"
            )
        hop = priority_hop(label, priority)
        return Hop(
            f"process {label}",
            hop.status,
            f"pid={state.pid} {hop.observed}",
            hop.expected,
            hop.detail,
        )
    observed = f"runs={state.runs} last exit={state.last_exit}"
    if state.interval_s:
        observed += f" every {state.interval_s}s"
    if not state.runs:
        return Hop(f"process {label}", Status.WARN, observed, "has run at least once")
    return Hop(
        f"process {label}",
        Status.FAIL if state.last_exit else Status.PASS,
        observed,
        "loaded; last run succeeded",
    )


def run(repo_root: Path) -> list[Hop]:
    """One block of hops per ``deploy/launchd/*.plist`` in the repo."""
    hops: list[Hop] = []
    for path in sorted((repo_root / "deploy" / "launchd").glob("*.plist")):
        try:
            cfg = parse_plist(path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - an unreadable plist is the finding
            hops.append(Hop(f"plist {path.stem}", Status.FAIL, short(exc), "valid plist"))
            continue
        label = str(cfg.get("Label") or path.stem)
        installed = load_installed(label, install_dir(cfg))
        state = query_job(label, is_daemon(cfg))
        hops.extend(installed_hop(label, cfg, installed, state.arguments))
        hops.append(process_hop(label, cfg, state))
    if not hops:
        hops.append(Hop("deploy/launchd", Status.FAIL, "no plists found", "repo plists present"))
    return hops
