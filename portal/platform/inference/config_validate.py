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
    "inject_temporal_context",
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
            defaults = wcfg.get("tool_model_defaults")
            if defaults is not None:
                if not isinstance(defaults, dict):
                    errors.append(f"workspace {wid}: `tool_model_defaults` must be a mapping")
                else:
                    for tool_name, target in defaults.items():
                        base, sep, variant = str(target or "").partition("::")
                        ws_target = workspaces.get(base)
                        if not isinstance(ws_target, dict) or (
                            sep and variant not in (ws_target.get("variants") or {})
                        ):
                            errors.append(
                                f"workspace {wid}: tool_model_defaults[{tool_name!r}] targets "
                                f"unknown workspace {target!r}"
                            )

    working_sets = doc.get("working_sets")
    if working_sets is not None:
        if not isinstance(working_sets, dict):
            errors.append("`working_sets:` present but not a mapping")
        elif isinstance(workspaces, dict):
            for set_id, spec in working_sets.items():
                if not isinstance(spec, dict):
                    errors.append(f"working_sets.{set_id}: not a mapping")
                    continue
                mode = spec.get("mode", "co_resident")
                if mode not in {"co_resident", "yield"}:
                    errors.append(f"working_sets.{set_id}: invalid mode {mode!r}")
                members = spec.get("workspaces")
                if not isinstance(members, list) or len(members) < 2:
                    errors.append(f"working_sets.{set_id}: `workspaces` needs at least 2 entries")
                    continue
                for member in members:
                    base, sep, variant = str(member or "").partition("::")
                    ws_target = workspaces.get(base)
                    if not isinstance(ws_target, dict) or (
                        sep and variant not in (ws_target.get("variants") or {})
                    ):
                        errors.append(f"working_sets.{set_id}: unknown workspace {member!r}")

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
