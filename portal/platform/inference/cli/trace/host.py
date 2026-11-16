"""Section 1 — every repo launchd job's installed plist and running process."""

from __future__ import annotations

import plistlib
import re
from pathlib import Path
from typing import Any

from .context import run_cmd
from .model import Hop, Status, short

_ENGINE_HINTS = ("omlx", "ollama")
_PID = re.compile(r'"PID"\s*=\s*(\d+)')
_DEFAULT_INSTALL_DIR = Path.home() / "Library" / "LaunchAgents"
_STANDARD_PRIORITY = 20


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


def expects_running(cfg: dict[str, Any]) -> bool:
    """KeepAlive / RunAtLoad jobs must have a pid; calendar jobs need not."""
    return bool(cfg.get("RunAtLoad") or cfg.get("KeepAlive"))


def is_engine(label: str) -> bool:
    return any(hint in label.lower() for hint in _ENGINE_HINTS)


def launchctl_pid(listing: str) -> int | None:
    """The pid from ``launchctl list <label>``, or None when unloaded/not running."""
    match = _PID.search(listing)
    return int(match.group(1)) if match else None


def parse_priority(output: str) -> int | None:
    """First integer line of ``ps -o pri= -p <pid>``."""
    for line in output.splitlines():
        text = line.strip()
        if text.isdigit():
            return int(text)
    return None


def priority_hop(label: str, priority: int) -> Hop:
    """Engines are never de-prioritised; nothing in the fleet should sit at Background."""
    engine = is_engine(label)
    expected = "pri>=20 (engines are never Background)"
    if priority >= _STANDARD_PRIORITY:
        return Hop(label, Status.PASS, f"pri={priority}", expected, "engine" if engine else "")
    if priority <= 4 or engine:
        return Hop(label, Status.FAIL, f"pri={priority}", expected, "de-prioritised")
    return Hop(label, Status.WARN, f"pri={priority}", expected)


def installed_hop(label: str, repo_cfg: dict[str, Any], install_dir: Path) -> list[Hop]:
    """The installed plist exists and carries the repo's ProcessType and env keys."""
    path = install_dir / f"{label}.plist"
    if not path.is_file():
        return [Hop(f"plist {label}", Status.FAIL, "installed=missing", "installed plist present")]
    installed = parse_plist(path.read_bytes())
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
    return hops


def process_hop(label: str, cfg: dict[str, Any]) -> Hop:
    """The job is running when it says it should be, at the priority it declares."""
    listing = run_cmd(["launchctl", "list", label], timeout=10)
    pid = launchctl_pid(listing.stdout) if listing.ok else None
    if pid is None:
        wanted = "running" if expects_running(cfg) else "scheduled"
        status = Status.FAIL if expects_running(cfg) else Status.PASS
        return Hop(f"process {label}", status, f"pid=none ({wanted})", wanted)
    ps = run_cmd(["ps", "-o", "pri=", "-p", str(pid)], timeout=10)
    priority = parse_priority(ps.stdout)
    if priority is None:
        return Hop(f"process {label}", Status.FAIL, f"pid={pid} pri=unreadable", "pri>=20")
    hop = priority_hop(label, priority)
    return Hop(
        f"process {label}", hop.status, f"pid={pid} {hop.observed}", hop.expected, hop.detail
    )


def run(repo_root: Path, install_dir: Path | None = None) -> list[Hop]:
    """One triple of hops per ``deploy/launchd/*.plist`` in the repo."""
    hops: list[Hop] = []
    directory = install_dir or _DEFAULT_INSTALL_DIR
    for path in sorted((repo_root / "deploy" / "launchd").glob("*.plist")):
        try:
            cfg = parse_plist(path.read_bytes())
        except Exception as exc:  # noqa: BLE001 - an unreadable plist is the finding
            hops.append(Hop(f"plist {path.stem}", Status.FAIL, short(exc), "valid plist"))
            continue
        label = str(cfg.get("Label") or path.stem)
        hops.extend(installed_hop(label, cfg, directory))
        hops.append(process_hop(label, cfg))
    if not hops:
        hops.append(Hop("deploy/launchd", Status.FAIL, "no plists found", "repo plists present"))
    return hops
