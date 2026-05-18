"""Source data loader — reads Portal 5 personas, workspaces, and MCP servers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


PORTAL_ROOT = Path(__file__).resolve().parent.parent.parent


def load_personas(personas_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return all persona dicts from config/personas/*.yaml, sorted by slug."""
    if personas_dir is None:
        personas_dir = PORTAL_ROOT / "config" / "personas"
    personas = []
    for yf in sorted(personas_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yf.read_text()) or {}
            if data.get("slug"):
                personas.append(data)
        except Exception as e:
            print(f"  [warn] Failed to load persona {yf.name}: {e}", file=sys.stderr)
    return personas


def load_workspaces() -> dict[str, dict[str, Any]]:
    """Return the WORKSPACES dict from the pipeline, keyed by workspace ID."""
    # Import from the pipeline package if available; otherwise parse the file
    try:
        sys.path.insert(0, str(PORTAL_ROOT))
        from portal_pipeline.router.workspaces import WORKSPACES  # noqa: PLC0415
        return dict(WORKSPACES)
    except ImportError:
        pass
    # Fallback: fetch from live pipeline /v1/models
    return {}


def load_mcp_servers(mcp_file: Path | None = None) -> list[dict[str, Any]]:
    """Return MCP server list from imports/openwebui/mcp-servers.json."""
    if mcp_file is None:
        mcp_file = PORTAL_ROOT / "imports" / "openwebui" / "mcp-servers.json"
    data = json.loads(mcp_file.read_text())
    return data.get("tool_servers", [])


def production_workspaces(workspaces: dict[str, dict]) -> dict[str, dict]:
    """Filter out bench-* workspaces for UI display."""
    return {k: v for k, v in workspaces.items() if not k.startswith("bench-")}
