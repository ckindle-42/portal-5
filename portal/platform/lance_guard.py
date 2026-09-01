"""Shared precondition for the LanceDB stores (TASK_VL_RUNTIME_LANDING_V4 P4).

`PORTAL5_LANCE_DIR` defaults to `/Volumes/data01/portal5_lance` — an external
volume. If that volume is not mounted, `os.makedirs(..., exist_ok=True)` silently
creates the tree on the boot disk and the store writes vectors into a path that
vanishes on the next real mount. A service that writes to an unmounted path is
worse than one that refuses to start, so callers gate on this before connecting.
"""

from __future__ import annotations

import os
from pathlib import Path


class LanceStoreUnavailableError(RuntimeError):
    """The configured LanceDB directory's volume is not mounted."""


def require_lance_dir(lance_dir: str) -> str:
    """Return `lance_dir` if its volume is mounted, else raise.

    The store dir itself need not exist yet (first run creates it), but its
    parent must — and if the path is under `/Volumes/<vol>`, `<vol>` must be a
    real mount, not a stray directory on the boot disk.
    """
    p = Path(lance_dir)
    parts = p.parts
    # A path under /Volumes/<vol> is only valid if <vol> is a real mount. This
    # is checked FIRST and unconditionally: a previous run that created the tree
    # on the boot disk (the exact failure this guard exists for) would otherwise
    # satisfy a `p.is_dir()` short-circuit and the mount check would never run.
    if len(parts) >= 3 and parts[1] == "Volumes":
        volume = Path("/Volumes") / parts[2]
        if not os.path.ismount(volume):
            raise LanceStoreUnavailableError(
                f"PORTAL5_LANCE_DIR={lance_dir}: volume {volume} is not mounted "
                f"(os.path.ismount({volume}) is False). A stray directory on the "
                "boot disk does not count. Mount the volume (or set "
                "PORTAL5_LANCE_DIR to a local path) before starting."
            )
    if p.is_dir():
        return lance_dir
    parent = p.parent
    if not parent.is_dir():
        raise LanceStoreUnavailableError(
            f"PORTAL5_LANCE_DIR={lance_dir}: parent {parent} does not exist."
        )
    return lance_dir
