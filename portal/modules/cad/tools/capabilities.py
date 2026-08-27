"""Runtime CAD capability detection.

Probes what is actually importable/available at process start — never asserts a
hardcoded platform claim like "arm64 means no OCP". `P5-CAD-ARM64-001` ("OCP has
no arm64 wheels, OpenSCAD only") was a *pip-wheel* artifact from early 2024;
conda-forge `ocp`/`occt` ship for linux-aarch64 and osx-arm64. If a conda/micromamba
env with cadquery/build123d/OCP is present (see Dockerfile.mcp's conda layer and
`CAD_CONDA_ENV_SITE_PACKAGES`), its site-packages dir is added to `sys.path` so
those modules become importable from the base interpreter — no hardcoded truth,
just "is it actually there right now."
"""

from __future__ import annotations

import functools
import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path

# Optional conda/micromamba env holding cadquery/build123d/OCP (installed via
# conda-forge — see Dockerfile.mcp). If set and present, its site-packages is
# added to sys.path before probing, so a pip-only base interpreter can still
# reach conda-installed packages.
CAD_CONDA_ENV_SITE_PACKAGES = os.getenv("CAD_CONDA_ENV_SITE_PACKAGES", "")


def _ensure_conda_env_on_path() -> None:
    if not CAD_CONDA_ENV_SITE_PACKAGES:
        return
    site_dir = Path(CAD_CONDA_ENV_SITE_PACKAGES)
    if site_dir.is_dir() and str(site_dir) not in sys.path:
        sys.path.insert(0, str(site_dir))


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
def cad_capabilities() -> dict:
    """What CAD backends are actually available right now, on this process.

    Never hardcodes a platform → capability mapping. Always re-probe (the cache
    exists only to avoid repeated import-spec lookups within one process
    lifetime, not to freeze a stale answer across environments).
    """
    _ensure_conda_env_on_path()

    caps = {
        "openscad": shutil.which("openscad") is not None,
        "trimesh": _has("trimesh"),
        "cadquery": _has("cadquery"),
        "build123d": _has("build123d"),
        "ocp": _has("OCP"),
        "cuda": _cuda_available(),
        "platform": platform.machine(),  # informational only, never gates a capability
    }
    caps["step_read"] = caps["ocp"] or caps["build123d"] or caps["cadquery"]
    caps["step_write"] = caps["step_read"]
    return caps
