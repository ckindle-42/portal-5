"""Module → service map derived from mcp_fleet plus host_jobs."""

from __future__ import annotations

import importlib.util
import os
import platform
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import typer

from portal.platform.inference.config import PORTAL_YAML, PortalConfig, load_portal_config

_KIND = frozenset({"host", "compose"})


@dataclass(frozen=True)
class ServiceRef:
    kind: str
    module: str
    ident: str
    port: int | None = None
    native_service: str | None = None
    fleet_id: str | None = None


def repo_root() -> Path:
    return PORTAL_YAML.parent.parent


def compose_dir() -> Path:
    return repo_root() / "deploy" / "portal-5"


def iter_services(cfg: PortalConfig) -> tuple[ServiceRef, ...]:
    """Every launchable service. Stdio IDE servers are omitted."""
    refs: list[ServiceRef] = []
    for server in cfg.mcp_fleet:
        if server.host_native and server.launchd_label:
            refs.append(
                ServiceRef(
                    "host",
                    server.module,
                    server.launchd_label,
                    server.port,
                    server.native_service,
                    server.id,
                )
            )
        elif server.compose_service:
            refs.append(
                ServiceRef(
                    "compose",
                    server.module,
                    server.compose_service,
                    server.port,
                    None,
                    server.id,
                )
            )
    for job in cfg.host_jobs:
        refs.append(ServiceRef("host", job.module, job.label, job.port, job.service, None))
    return tuple(sorted(refs, key=lambda ref: (ref.module, ref.kind, ref.ident)))


def active_modules(enabled: list[str] | None = None) -> set[str]:
    """Enabled discipline modules plus platform, which is always on."""
    from portal.platform.wiki.adapters.modules import enabled_modules

    mods = set(enabled_modules() if enabled is None else enabled)
    mods.add("platform")
    return mods


def select_services(
    cfg: PortalConfig,
    *,
    want_enabled: bool,
    kind: str | None = None,
    modules: list[str] | None = None,
    enabled: list[str] | None = None,
) -> list[ServiceRef]:
    running = active_modules(enabled)
    chosen: list[ServiceRef] = []
    for ref in iter_services(cfg):
        if kind is not None and ref.kind != kind:
            continue
        if modules is not None and ref.module not in modules:
            continue
        is_on = ref.module in running
        if is_on == want_enabled:
            chosen.append(ref)
    return chosen


def services_for_module(cfg: PortalConfig, name: str) -> list[ServiceRef]:
    return [ref for ref in iter_services(cfg) if ref.module == name]


def up_plan(
    cfg: PortalConfig, enabled: list[str] | None = None
) -> tuple[list[ServiceRef], list[ServiceRef]]:
    """Services to start, then services to stop, for this enabled set."""
    start = select_services(cfg, want_enabled=True, enabled=enabled)
    stop = select_services(cfg, want_enabled=False, enabled=enabled)
    return start, stop


def stop_argv(ref: ServiceRef, *, uid: int | None = None) -> list[list[str]]:
    """Reversible stop. Host jobs are bootout, never plist deletion."""
    if ref.kind == "compose":
        return [["docker", "compose", "stop", ref.ident]]
    user = os.getuid() if uid is None else uid
    return [["launchctl", "bootout", f"gui/{user}/{ref.ident}"]]


def start_argv(
    ref: ServiceRef, *, uid: int | None = None, plist: Path | None = None
) -> list[list[str]]:
    if ref.kind == "compose":
        return [["docker", "compose", "up", "-d", "--no-deps", ref.ident]]
    user = os.getuid() if uid is None else uid
    domain = f"gui/{user}"
    cmds: list[list[str]] = []
    if plist is not None:
        cmds.append(["launchctl", "bootstrap", domain, str(plist)])
    cmds.append(["launchctl", "kickstart", "-k", f"{domain}/{ref.ident}"])
    return cmds


def _plist(ref: ServiceRef) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{ref.ident}.plist"


def _healthy(port: int | None) -> bool:
    if port is None:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as resp:
            return int(resp.status) < 500
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _vl_ready() -> bool:
    names = ("mlx_embeddings.models.qwen3_vl", "torchvision", "fastapi", "uvicorn")
    return all(importlib.util.find_spec(name) for name in names)


def skip_reason(ref: ServiceRef, repo: Path | None = None) -> str | None:
    """Why an enabled host service should not be started on this machine."""
    root = repo if repo is not None else repo_root()
    service = ref.native_service or ""
    if service == "mlx-speech":
        ready = platform.machine() == "arm64" and importlib.util.find_spec("mlx_audio")
        if not ready or not (root / "scripts" / "mlx-speech.py").is_file():
            return "mlx-speech runtime not installed"
    elif service == "mlx-transcribe":
        if platform.machine() != "arm64" or not (root / "scripts" / "mlx-transcribe.py").is_file():
            return "mlx-transcribe not installed"
    elif service == "vl-retrieval" and not _vl_ready():
        return "VL retrieval deps missing"
    elif service == "eg2-embedding":
        eg2 = Path(os.environ.get("EG2_VENV", Path.home() / ".portal5" / "eg2-venv"))
        if not (eg2 / "bin" / "python3").is_file():
            return "EG2 venv missing"
    elif ref.kind == "host" and not service and not _plist(ref).is_file():
        return "not installed"
    return None


def _run(argv: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=cwd, check=False, capture_output=True, text=True)


def _ensure_plist(ref: ServiceRef) -> str:
    root = repo_root()
    service = ref.native_service or ""
    port = "" if ref.port is None else str(ref.port)
    script = "\n".join(
        [
            f"export PORTAL_ROOT={shlex.quote(str(root))}",
            'source "$PORTAL_ROOT/scripts/lib/util.sh"',
            "_ensure_native_mcp_service "
            f"{shlex.quote(service)} {shlex.quote(ref.ident)} "
            f"{shlex.quote(port)} {shlex.quote(service)}",
        ]
    )
    proc = subprocess.run(
        ["bash", "-c", script], cwd=root, check=False, capture_output=True, text=True
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "launchd registration failed").strip().splitlines()
        return f"{ref.ident}: {tail[-1]}"
    return f"{ref.ident}: launchd supervision enabled"


def _kickstart(ref: ServiceRef) -> str:
    if _healthy(ref.port):
        return f"{ref.ident}: running"
    plist = _plist(ref)
    for argv in start_argv(ref, plist=plist if plist.is_file() else None):
        _run(argv)
    return f"{ref.ident}: kickstarted"


def apply_one(ref: ServiceRef, *, start: bool) -> str:
    if not start:
        argv = stop_argv(ref)[0]
        cwd = compose_dir() if ref.kind == "compose" else None
        _run(argv, cwd=cwd)
        verb = "stopped" if ref.kind == "compose" else "bootout"
        return f"{ref.ident}: {verb}"
    reason = skip_reason(ref)
    if reason:
        return f"{ref.ident}: {reason}"
    if ref.kind == "compose":
        _run(start_argv(ref)[0], cwd=compose_dir())
        return f"{ref.ident}: started"
    if ref.native_service and not _plist(ref).is_file():
        return _ensure_plist(ref)
    return _kickstart(ref)


def apply_module(name: str, *, start: bool) -> list[str]:
    cfg = load_portal_config(_force_reload=True)
    return [apply_one(ref, start=start) for ref in services_for_module(cfg, name)]


def status_rows(cfg: PortalConfig, runtime: dict[str, str] | None = None) -> list[str]:
    running = active_modules()
    lines: list[str] = []
    for ref in iter_services(cfg):
        state = "enabled" if ref.module in running else "disabled"
        if runtime is None:
            seen = "up" if _healthy(ref.port) else "down"
            if ref.port is None:
                seen = "n/a"
        else:
            seen = runtime.get(ref.ident, "down")
        port = f":{ref.port}" if ref.port is not None else ""
        lines.append(
            f"{ref.module:<14} {state:<10} {seen:<6} {ref.kind:<8} {ref.ident} {port}".rstrip()
        )
    return lines


def _checked_kind(kind: str | None) -> str | None:
    if kind is not None and kind not in _KIND:
        typer.echo("--kind is host or compose", err=True)
        raise typer.Exit(code=2)
    return kind


def _print_selected(
    cfg: PortalConfig, *, want_enabled: bool, kind: str | None, module: str | None
) -> None:
    modules = [module] if module else None
    for ref in select_services(cfg, want_enabled=want_enabled, kind=kind, modules=modules):
        typer.echo(ref.ident)


def _apply_selected(
    cfg: PortalConfig, *, kind: str | None, module: str | None, stop_only: bool
) -> None:
    modules = [module] if module else None
    if not stop_only:
        for ref in select_services(cfg, want_enabled=True, kind=kind, modules=modules):
            typer.echo(apply_one(ref, start=True))
    for ref in select_services(cfg, want_enabled=False, kind=kind, modules=modules):
        typer.echo(apply_one(ref, start=False))


def run_services_cli(
    *,
    enabled: bool,
    disabled: bool,
    kind: str | None,
    module: str | None,
    apply: bool,
    stop_only: bool,
    status: bool,
) -> None:
    kind = _checked_kind(kind)
    cfg = load_portal_config(_force_reload=True)
    if status:
        for line in status_rows(cfg):
            typer.echo(line)
        return
    if enabled and disabled:
        typer.echo("pass only one of --enabled and --disabled", err=True)
        raise typer.Exit(code=2)
    if apply:
        _apply_selected(cfg, kind=kind, module=module, stop_only=stop_only)
        return
    if not enabled and not disabled:
        typer.echo("pass --enabled, --disabled, --status, or --apply", err=True)
        raise typer.Exit(code=2)
    _print_selected(cfg, want_enabled=enabled, kind=kind, module=module)
