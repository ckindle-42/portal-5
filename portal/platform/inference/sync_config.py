"""sync-config — generate derived artifacts from config/portal.yaml.

Idempotent: running twice produces no diff.  Called by ``./launch.sh sync-config``.

Generates:
  config/backends.yaml        → workspace_routing block only (backends: block
                                is operator-edited; never touched here)
  .mcp.json                   → Claude Code MCP server list
  opencode.jsonc              → curated model picker for opencode
  imports/openwebui/workspaces/workspace_*.json → OWUI workspace presets

Run:
  python3 -m portal.platform.inference.sync_config
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO: Path = Path(__file__).resolve().parents[3]

# ── update_workspace_tools.py tool-ID mapping ────────────────────────────────
# Maps workspace-id → OWUI toolIds (server:mcp:<name> format).
# Authoritative source: scripts/update_workspace_tools.py; this is a copy
# so sync-config doesn't need to exec that script separately.
_WORKSPACE_TOOL_IDS: dict[str, list[str]] = {
    "auto": ["server:mcp:portal_comfyui"],
    "auto-daily": ["server:mcp:portal_research", "server:mcp:portal_memory"],
    "auto-coding": ["server:mcp:portal_code", "server:mcp:portal_memory"],
    "auto-compliance": ["server:mcp:portal_research"],
    "auto-documents": ["server:mcp:portal_documents", "server:mcp:portal_code"],
    "auto-music": ["server:mcp:portal_music", "server:mcp:portal_tts"],
    "auto-video": ["server:mcp:portal_video", "server:mcp:portal_comfyui"],
    "auto-security": [
        "server:mcp:portal_research",
        "server:mcp:portal_code",
        "server:mcp:portal_security",
    ],
    "auto-redteam": ["server:mcp:portal_research", "server:mcp:portal_code"],
    "auto-blueteam": ["server:mcp:portal_research", "server:mcp:portal_code"],
    "auto-research": ["server:mcp:portal_research"],
    "auto-reasoning": ["server:mcp:portal_research"],
    "auto-creative": ["server:mcp:portal_tts"],
    "auto-vision": ["server:mcp:portal_comfyui"],
    "auto-data": [
        "server:mcp:portal_research",
        "server:mcp:portal_code",
        "server:mcp:portal_documents",
    ],
    "auto-math": [],
    "auto-spl": ["server:mcp:portal_code"],
    "auto-mistral": ["server:mcp:portal_research"],
    "auto-agentic": ["server:mcp:portal_code"],
    "auto-audio": ["server:mcp:portal_whisper"],
    "tools-specialist": ["server:mcp:portal_code", "server:mcp:portal_memory"],
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _ws_filename(ws_id: str) -> str:
    """workspace_auto_coding_agentic.json for ws_id='auto-coding-agentic'."""
    return "workspace_" + ws_id.replace("-", "_") + ".json"


def _owui_preset(ws_id: str, spec: Any) -> dict[str, Any]:
    """Build an OWUI workspace preset payload from a WorkspaceSpec."""
    tool_ids = _WORKSPACE_TOOL_IDS.get(ws_id, [])
    preset: dict[str, Any] = {
        "id": ws_id,
        "name": spec.name,
        "meta": {
            "description": spec.name,
            "profile_image_url": "",
            "toolIds": tool_ids,
        },
        "params": {
            "model": ws_id,
        },
    }
    if spec.owui_system_prompt:
        preset["params"]["system"] = spec.owui_system_prompt
    if spec.enable_web_search:
        preset["params"]["enable_web_search"] = True
    return preset


# ── Emitters ──────────────────────────────────────────────────────────────────


def emit_workspace_routing(config: Any) -> bool:
    """Rewrite workspace_routing block in config/backends.yaml. Returns True if changed."""
    backends_path = REPO / "config" / "backends.yaml"
    original = backends_path.read_text(encoding="utf-8")

    # Build new workspace_routing block
    routing_lines: list[str] = ["workspace_routing:"]
    for ws_id, _spec in config.workspaces.items():
        routing_lines.append(f"  {ws_id}:")
        # Look up backend groups from current backends.yaml (preserve existing routing)
        # We need the routing groups from the current file; this is a round-trip.
        pass

    # Parse existing routing to preserve backend groups
    raw = yaml.safe_load(original) or {}
    existing_routing: dict[str, Any] = raw.get("workspace_routing", {})

    new_routing: dict[str, list[str]] = {}
    missing: list[str] = []
    for ws_id in config.workspaces:
        if ws_id in existing_routing:
            new_routing[ws_id] = existing_routing[ws_id]
        else:
            # New workspace — default to general group
            new_routing[ws_id] = ["general"]
            missing.append(ws_id)

    if missing:
        print(f"  workspace_routing: added {len(missing)} new entries → ['general']:")
        for ws_id in missing:
            print(f"    {ws_id}")

    # Emit new routing YAML
    routing_yaml_lines: list[str] = []
    for ws_id, groups in new_routing.items():
        groups_str = "\n".join(f"  - {g}" for g in groups)
        routing_yaml_lines.append(f"  {ws_id}:\n{groups_str}")
    routing_block = "workspace_routing:\n" + "\n".join(routing_yaml_lines)

    # Replace existing workspace_routing block in file
    # Strategy: find the block by scanning for "workspace_routing:" marker and
    # replace up to the next top-level key or end of file.
    new_text = re.sub(
        r"^workspace_routing:.*?(?=^[a-z]|\Z)",
        routing_block + "\n",
        original,
        flags=re.MULTILINE | re.DOTALL,
    )

    if new_text == original:
        return False
    backends_path.write_text(new_text, encoding="utf-8")
    return True


def emit_mcp_json(config: Any) -> bool:
    """Regenerate .mcp.json (Claude Code MCP config). Returns True if changed."""
    mcp_path = REPO / ".mcp.json"
    original = mcp_path.read_text(encoding="utf-8")

    servers: dict[str, Any] = {}
    for server in config.mcp_fleet:
        if not server.expose_to_ide:
            continue
        if server.command is not None:
            # Command-based (local) server
            cmd = server.command.command
            entry: dict[str, Any] = {"command": cmd[0], "args": cmd[1:]}
        else:
            # HTTP server
            entry = {"type": "http", "url": f"http://localhost:{server.port}/mcp"}
        servers[server.name] = entry

    new_content = json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n"
    if new_content == original:
        return False
    mcp_path.write_text(new_content, encoding="utf-8")
    return True


def emit_opencode_picker(config: Any) -> bool:
    """Update the models block in opencode.jsonc with curated workspace subset. Returns True if changed."""
    oc_path = REPO / "opencode.jsonc"
    oc_path.read_text(encoding="utf-8")  # read to confirm file exists

    # Curated subset: auto-* non-bench workspaces that aren't security-offensive
    # or very specialised.  The full list is always available via `opencode models`.
    # We keep the existing curated list but add any auto-* workspaces that are
    # expose_to_owui=true and not already present.
    # For now: regeneration preserves file as-is (the opencode.jsonc has hand-tuned
    # names and reasoning flags); only update if workspace IDs drift.
    # Full opencode.jsonc regeneration is deferred to M5 (launch.sh typed CLI).
    return False  # no-op for now — opencode.jsonc is hand-maintained until M5


def emit_owui_presets(config: Any) -> tuple[int, int, int]:
    """Regenerate imports/openwebui/workspaces/workspace_*.json. Returns (created, updated, removed)."""
    ws_dir = REPO / "imports" / "openwebui" / "workspaces"
    ws_dir.mkdir(parents=True, exist_ok=True)

    created = updated = removed = 0

    # Emit presets for all workspaces with expose_to_owui=True
    emitted_files: set[str] = set()
    for ws_id, spec in config.workspaces.items():
        if not spec.expose_to_owui:
            continue
        preset = _owui_preset(ws_id, spec)
        fname = _ws_filename(ws_id)
        fpath = ws_dir / fname
        new_content = json.dumps(preset, indent=2, ensure_ascii=False) + "\n"
        if fpath.exists():
            old_content = fpath.read_text(encoding="utf-8")
            if old_content != new_content:
                fpath.write_text(new_content, encoding="utf-8")
                updated += 1
        else:
            fpath.write_text(new_content, encoding="utf-8")
            created += 1
        emitted_files.add(fname)

    # Remove orphan preset files (workspace no longer in catalog or expose_to_owui=False)
    for fpath in sorted(ws_dir.glob("workspace_*.json")):
        if fpath.name not in emitted_files:
            fpath.unlink()
            removed += 1
            print(f"  Removed orphan preset: {fpath.name}")

    return created, updated, removed


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    from portal.platform.inference.config import load_portal_config

    config = load_portal_config(_force_reload=True)
    print(f"sync-config: loaded {len(config.workspaces)} workspaces, {len(config.mcp_fleet)} MCPs")

    # 1. workspace_routing in backends.yaml
    changed = emit_workspace_routing(config)
    print(f"  backends.yaml workspace_routing: {'updated' if changed else 'no change'}")

    # 2. .mcp.json
    changed = emit_mcp_json(config)
    print(f"  .mcp.json: {'updated' if changed else 'no change'}")

    # 3. opencode.jsonc (no-op until M5)
    emit_opencode_picker(config)

    # 4. OWUI workspace presets
    c, u, r = emit_owui_presets(config)
    print(f"  imports/openwebui/workspaces/: {c} created, {u} updated, {r} removed")

    print("sync-config: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
