"""Tool inventory — the real Kali arsenal, not a guess (Phase 1).

Two sources, reconciled:
  1. Declared — config/tool_catalog.yaml, curated from the lane
     system_prompt_append toolchains + _LAB_SERVICE_PROBES commands.
  2. Live-verified (optional) — a single batched `which`/`command -v`
     over the catalog in the sandbox. dry_run (default) never touches
     the lab; everything reads 'unknown' and the declared catalog is
     authoritative.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[5]
_CATALOG_PATH = _REPO_ROOT / "config" / "tool_catalog.yaml"


@lru_cache(maxsize=1)
def load_tool_catalog() -> list[dict[str, Any]]:
    """Parse config/tool_catalog.yaml. Cached — the file doesn't change at runtime."""
    data = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    return data.get("tools", [])


def tools_for_service(service: str) -> list[dict[str, Any]]:
    """Tools applicable to a given service key (matches _LAB_SERVICE_PROBES keys)."""
    return [t for t in load_tool_catalog() if service in (t.get("targets_services") or [])]


def tools_for_phase(phase: str) -> list[dict[str, Any]]:
    """Tools applicable to a given engagement phase."""
    return [t for t in load_tool_catalog() if t.get("phase") == phase]


def verify_tools_present(dry_run: bool = True) -> dict[str, bool | None]:
    """Batched presence check in the sandbox — one lab_dispatch call, not
    one per tool. dry_run (default) or no reachable lab → every entry is
    None ('unknown'); the declared catalog stays authoritative.

    Returns {tool_name: True|False|None}.
    """
    names = [t["name"] for t in load_tool_catalog()]
    if dry_run:
        return dict.fromkeys(names, None)

    from portal.modules.security.core._data import _lab_mcp_call

    # One batched command: for each tool, print "NAME:FOUND" or "NAME:MISSING".
    checks = "; ".join(
        f'command -v {name} >/dev/null 2>&1 && echo "{name}:FOUND" || echo "{name}:MISSING"'
        for name in names
    )
    result = _lab_mcp_call(checks, timeout=60, dry_run=False)
    presence: dict[str, bool | None] = dict.fromkeys(names, None)
    if not result.get("ok"):
        return presence
    for line in (result.get("output") or "").splitlines():
        line = line.strip()
        if ":FOUND" in line:
            presence[line.split(":FOUND")[0]] = True
        elif ":MISSING" in line:
            presence[line.split(":MISSING")[0]] = False
    return presence
