"""Fast, self-contained portal.yaml validator used as a pre-regeneration gate.

Independent of scripts/validate_system.py: this runs on the ``sync-config`` hot path
and must be fast and dependency-light. It checks the invariants whose violation would
corrupt derived artifacts. Returns a list of error strings (empty == valid); never
raises on malformed input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_BOOL_KEYS = (
    "expose_to_owui",
    "inject_memory",
    "auto_rag",
    "memory_writeback",
    "memory_writeback_all",
)


def validate_config(path: str | Path = "config/portal.yaml") -> list[str]:
    errors: list[str] = []
    p = Path(path)
    if not p.exists():
        return [f"config not found: {p}"]
    try:
        doc: Any = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return ["top-level YAML is not a mapping"]

    workspaces = doc.get("workspaces")
    if not isinstance(workspaces, dict) or not workspaces:
        errors.append("`workspaces:` missing or not a mapping")
    else:
        for wid, wcfg in workspaces.items():
            if not isinstance(wcfg, dict):
                errors.append(f"workspace {wid}: not a mapping")
                continue
            if not str(wcfg.get("model_hint") or "").strip():
                errors.append(f"workspace {wid}: empty/missing model_hint")
            for bk in _BOOL_KEYS:
                if bk in wcfg and not isinstance(wcfg[bk], bool):
                    errors.append(f"workspace {wid}: `{bk}` must be a bool")

    servers = doc.get("mcp_servers")
    if servers is None:
        servers = doc.get("mcp")  # tolerate either key name
    if servers is not None:
        if not isinstance(servers, list):
            errors.append("`mcp_servers:` present but not a list")
        else:
            seen_ids: set[str] = set()
            seen_ports: dict[int, str] = {}
            for entry in servers:
                if not isinstance(entry, dict):
                    errors.append("mcp server entry is not a mapping")
                    continue
                sid = str(entry.get("id", "")).strip()
                if not sid:
                    errors.append("mcp server with empty id")
                elif sid in seen_ids:
                    errors.append(f"duplicate mcp server id: {sid}")
                else:
                    seen_ids.add(sid)
                port = entry.get("port")
                if port is not None:
                    if not isinstance(port, int) or not (1 <= port <= 65535):
                        errors.append(f"mcp server {sid}: invalid port {port!r}")
                    elif port in seen_ports:
                        errors.append(
                            f"mcp server {sid}: port {port} collides with {seen_ports[port]}"
                        )
                    else:
                        seen_ports[port] = sid
    return errors
