"""Runtime CAD capability detection.

Probes what is actually importable/available at process start — never asserts a
hardcoded platform claim like "arm64 means no OCP". build123d/OCP are pip-installed
arm64 wheels in the dedicated CAD image (Dockerfile.cad); this module only reports
whether they, the OpenSCAD binary (and its backend), and the build123d-mcp engine
are really there right now.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import platform
import shutil
import subprocess  # noqa: S404 — fixed argv, no shell


def _has(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _cuda_available() -> bool:
    if not _has("torch"):
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 — torch import/probe failures mean "no cuda"
        return False


@functools.lru_cache(maxsize=1)
def cad_capabilities() -> dict[str, bool | str]:
    """What CAD backends are actually available right now, on this process.

    Never hardcodes a platform → capability mapping. The cache only avoids repeated
    import-spec / subprocess probes within one process lifetime; the live engine
    state is added by `cad_status()`, uncached.
    """
    openscad_bin = os.getenv("OPENSCAD_BIN", "openscad")
    openscad_found = shutil.which(openscad_bin) is not None
    caps: dict[str, bool | str] = {
        "openscad": openscad_found,
        "openscad_bin": openscad_bin,
        "openscad_version": _openscad_cmd(openscad_bin, "--version") if openscad_found else "",
        "openscad_backend": _openscad_backend(openscad_bin) if openscad_found else "",
        "trimesh": _has("trimesh"),
        "cadquery": _has("cadquery"),
        "build123d": _has("build123d"),
        "ocp": _has("OCP"),
        "cuda": _cuda_available(),
        "build123d_mcp": shutil.which("build123d-mcp") is not None,
        "arch": platform.machine(),  # informational only, never gates a capability
    }
    caps["step_read"] = caps["ocp"] or caps["build123d"] or caps["cadquery"]
    caps["step_write"] = caps["step_read"]
    return caps


def _openscad_cmd(binary: str, flag: str) -> str:
    try:
        proc = subprocess.run(  # noqa: S603
            [binary, flag], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (proc.stdout + proc.stderr).strip()
    return out.splitlines()[0] if flag == "--version" and out else out


def _openscad_backend(binary: str) -> str:
    """The configured backend if this binary advertises --backend, else CGAL."""
    if "--backend" in _openscad_cmd(binary, "--help"):
        return os.getenv("CAD_OPENSCAD_BACKEND", "cgal")
    return "cgal"


def cad_status() -> dict[str, bool | str]:
    """cad_capabilities() plus the live (uncached) build123d engine state."""
    caps = dict(cad_capabilities())
    try:
        from portal.modules.cad.tools import b123d_bridge

        caps["engine"] = bool(b123d_bridge.engine_alive())
    except Exception:  # noqa: BLE001 — bridge absent/unreachable means no engine
        caps["engine"] = False
    return caps
