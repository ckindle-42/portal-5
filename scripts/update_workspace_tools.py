#!/usr/bin/env python3
"""Update workspace toolIds using the configured Open WebUI server map."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_owui_tools = importlib.import_module("portal.platform.inference.owui_tools")
all_tools_dead = _owui_tools.all_tools_dead
compute_tool_ids = _owui_tools.compute_tool_ids


def _portal_yaml_path() -> Path:
    for candidate in (Path("/config/portal.yaml"), Path("config/portal.yaml")):
        if candidate.exists():
            return candidate
    return REPO / "config" / "portal.yaml"


def load_workspace_raw_tools() -> dict[str, list[str]]:
    """Return raw tool names for every base workspace in portal.yaml."""
    config = yaml.safe_load(_portal_yaml_path().read_text(encoding="utf-8")) or {}
    return {
        workspace_id: (spec.get("tools") or [])
        for workspace_id, spec in (config.get("workspaces") or {}).items()
    }


def main() -> int:
    """Update workspace JSON files with current toolId mappings."""
    workspace_dir = Path("imports/openwebui/workspaces")
    if not workspace_dir.exists():
        workspace_dir = REPO / "imports" / "openwebui" / "workspaces"
    if not workspace_dir.exists():
        print(f"WARNING: workspace directory not found: {workspace_dir}")
        return 1

    raw_tools_by_workspace = load_workspace_raw_tools()
    errors = 0
    for workspace_file in sorted(workspace_dir.glob("workspace_*.json")):
        try:
            data = json.loads(workspace_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: {workspace_file.name}: {exc}")
            errors += 1
            continue

        workspace_id = data.get("id", "")
        if workspace_id not in raw_tools_by_workspace:
            print(f"SKIP: {workspace_file.name} (id={workspace_id!r} not in config/portal.yaml)")
            continue

        tool_ids = compute_tool_ids(raw_tools_by_workspace[workspace_id])
        data.setdefault("meta", {})
        if data["meta"].get("toolIds") == tool_ids:
            continue
        data["meta"]["toolIds"] = tool_ids
        try:
            workspace_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"Updated {workspace_file.name}: toolIds={tool_ids}")
        except OSError as exc:
            print(f"ERROR writing {workspace_file.name}: {exc}")
            errors += 1

    if errors:
        print(f"Done with {errors} error(s).")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
