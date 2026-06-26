#!/usr/bin/env python3
"""One-shot migration: build config/portal.yaml from current sources.

Reads:
  portal_pipeline/router/workspaces.py  (WORKSPACES literal → workspace catalog)
  portal_pipeline/tool_registry.py      (MCP_SERVERS → pipeline-exposed MCPs)
  .mcp.json                             (full IDE/Claude Code fleet)
  imports/openwebui/workspaces/         (existing OWUI presets → params.system, enable_web_search)

Writes:
  config/portal.yaml

This script is run ONCE during M1 migration.  After portal.yaml exists, all
further updates go through `./launch.sh sync-config`.

Run from repo root:
  python3 scripts/migrate_to_portal_yaml.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from portal_pipeline.router.workspaces import WORKSPACES

# ── Gather OWUI preset metadata ───────────────────────────────────────────────

def _load_owui_metadata() -> dict[str, dict]:
    """Read existing workspace JSON files for params.system and enable_web_search."""
    data: dict[str, dict] = {}
    ws_dir = REPO / "imports" / "openwebui" / "workspaces"
    for f in sorted(ws_dir.glob("workspace_*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        ws_id = d.get("id", "")
        if not ws_id:
            continue
        params = d.get("params", {})
        data[ws_id] = {
            "system": params.get("system"),
            "enable_web_search": bool(params.get("enable_web_search", False)),
        }
    return data


# ── Orphan detection ──────────────────────────────────────────────────────────

def _classify_workspaces(owui_meta: dict[str, dict]) -> tuple[set[str], set[str], set[str]]:
    """Return (live_ws_ids, bench_with_preset, orphan_preset_ids).

    live_ws_ids       — workspace IDs currently in WORKSPACES
    bench_with_preset — bench-* workspace IDs that have an existing JSON preset
    orphan_preset_ids — JSON preset IDs for workspaces no longer in WORKSPACES
    """
    live = set(WORKSPACES.keys())
    bench_with_preset = {ws_id for ws_id in owui_meta if ws_id.startswith("bench-") and ws_id in live}
    orphan = {ws_id for ws_id in owui_meta if ws_id not in live}
    return live, bench_with_preset, orphan


# ── MCP fleet construction ────────────────────────────────────────────────────

# The .mcp.json command-based servers (IDE/Claude Code only)
_IDE_COMMAND_SERVERS: list[dict] = [
    {
        "id": "filesystem",
        "name": "filesystem",
        "expose_to_pipeline": False,
        "expose_to_ide": True,
        "command": {
            "type": "local",
            "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "${HOME}/projects", "/tmp"],
        },
    },
    {
        "id": "fetch",
        "name": "fetch",
        "expose_to_pipeline": False,
        "expose_to_ide": True,
        "command": {
            "type": "local",
            "command": ["uvx", "mcp-fetch"],
        },
    },
    {
        "id": "git",
        "name": "git",
        "expose_to_pipeline": False,
        "expose_to_ide": True,
        "command": {
            "type": "local",
            "command": ["uvx", "mcp-server-git", "--repository", "${HOME}/projects/portal-5"],
        },
    },
    {
        "id": "docker",
        "name": "docker",
        "expose_to_pipeline": False,
        "expose_to_ide": True,
        "command": {
            "type": "local",
            "command": ["npx", "-y", "mcp-docker-server"],
        },
    },
]

# Canonical port table (ground truth for all HTTP MCP servers)
# Reconciles drift between tool_registry (pipeline id) and .mcp.json (IDE name)
_HTTP_MCP_FLEET: list[dict] = [
    # Port  Pipeline-id      IDE-name                  pipeline  ide
    {"id": "comfyui",        "name": "portal-comfyui",        "port": 8910, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "video",          "name": "portal-video",          "port": 8911, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "music",          "name": "portal-music",          "port": 8912, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "documents",      "name": "portal-documents",      "port": 8913, "expose_to_pipeline": True,  "expose_to_ide": True},
    # 8914: pipeline calls it "execution"; .mcp.json calls it "portal-sandbox" — canonical: execution
    {"id": "execution",      "name": "portal-sandbox",        "port": 8914, "expose_to_pipeline": True,  "expose_to_ide": True,
     "aliases": ["sandbox"]},
    {"id": "whisper",        "name": "portal-whisper",        "port": 8915, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "tts",            "name": "portal-tts",            "port": 8916, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "security",       "name": "portal-security",       "port": 8919, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "memory",         "name": "portal-memory",         "port": 8920, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "rag",            "name": "portal-rag",            "port": 8921, "expose_to_pipeline": True,  "expose_to_ide": True},
    {"id": "research",       "name": "portal-research",       "port": 8922, "expose_to_pipeline": True,  "expose_to_ide": True},
    # 8923 browser: pipeline deliberately excludes it (raw browser tools not model-callable),
    # but IDE uses it for Playwright automation
    {"id": "browser",        "name": "portal-browser",        "port": 8923, "expose_to_pipeline": False, "expose_to_ide": True},
    # 8924: pipeline calls it "mlx_transcribe"; .mcp.json calls it "portal-mlx-transcribe"
    {"id": "mlx_transcribe", "name": "portal-mlx-transcribe", "port": 8924, "expose_to_pipeline": True,  "expose_to_ide": True},
    # 8925 reranker: internal, not exposed to models or IDE
    {"id": "reranker",       "name": "portal-reranker",       "port": 8925, "expose_to_pipeline": False, "expose_to_ide": False},
    {"id": "cad_render",     "name": "portal-cad-render",     "port": 8926, "expose_to_pipeline": True,  "expose_to_ide": False},
    # 8927 proxmox: IDE-only (Proxmox VM control is not model-callable from pipeline)
    {"id": "proxmox",        "name": "portal-proxmox",        "port": 8927, "expose_to_pipeline": False, "expose_to_ide": True},
    {"id": "pipeline",       "name": "portal-pipeline",       "port": 8928, "expose_to_pipeline": True,  "expose_to_ide": True},
]


def _build_mcp_fleet() -> list[dict]:
    fleet: list[dict] = list(_IDE_COMMAND_SERVERS)
    fleet.extend(_HTTP_MCP_FLEET)
    return fleet


# ── Workspace catalog construction ────────────────────────────────────────────

def _workspace_entry(
    ws_id: str,
    ws: dict,
    owui_meta: dict[str, dict],
    bench_with_preset: set[str],
    orphan_ids: set[str],
    web_search_enabled: set[str],
) -> dict:
    """Build one workspace entry for portal.yaml."""
    entry: dict = {}

    # Copy all original WORKSPACES fields in definition order (readable YAML)
    for key in ["name", "description", "model_hint"]:
        if key in ws:
            entry[key] = ws[key]

    # Numeric/bool tuning knobs
    for key in [
        "predict_limit", "context_limit", "max_concurrent",
        "keep_alive", "temperature", "top_p", "top_k", "min_p",
        "repeat_penalty", "seed",
        "think", "emits_reasoning",
        "system_prompt_append",
    ]:
        if key in ws:
            entry[key] = ws[key]

    # Tools whitelist (always include, even if empty)
    entry["tools"] = list(ws.get("tools", []))

    # Chain hops (multi-model workspaces)
    if "chain" in ws:
        entry["chain"] = list(ws["chain"])

    # --- portal.yaml-only fields ---

    # expose_to_owui: true for all non-bench, and for bench workspaces that
    # currently have a workspace JSON preset.  Orphan presets are NOT emitted.
    if ws_id.startswith("bench-"):
        entry["expose_to_owui"] = ws_id in bench_with_preset
    else:
        entry["expose_to_owui"] = True

    # enable_web_search: preserve current OWUI preset value
    entry["enable_web_search"] = ws_id in web_search_enabled

    # owui_system_prompt: preserve existing params.system from current JSON,
    # or leave absent (None → omitted by sync-config) for new workspaces.
    existing_system = owui_meta.get(ws_id, {}).get("system")
    if existing_system:
        entry["owui_system_prompt"] = existing_system

    return entry


# ── YAML dumper that uses block literals for multiline strings ────────────────

class _BlockDumper(yaml.Dumper):
    pass


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    if "\n" in data or len(data) > 120:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _str_representer)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    owui_meta = _load_owui_metadata()
    live, bench_with_preset, orphan_ids = _classify_workspaces(owui_meta)
    web_search_enabled = {ws_id for ws_id, m in owui_meta.items() if m["enable_web_search"]}

    print(f"Live workspaces: {len(live)}")
    print(f"Bench with existing OWUI preset: {len(bench_with_preset)}")
    print(f"Orphan OWUI presets (will be dropped): {len(orphan_ids)}")
    if orphan_ids:
        print(f"  Orphans: {sorted(orphan_ids)}")

    # Build workspace catalog
    workspaces: dict[str, dict] = {}
    for ws_id, ws in WORKSPACES.items():
        workspaces[ws_id] = _workspace_entry(
            ws_id, ws, owui_meta, bench_with_preset, orphan_ids, web_search_enabled
        )

    # Build MCP fleet
    mcp_fleet = _build_mcp_fleet()

    portal = {
        "# Portal 5 single configuration source of truth": None,
        "# Edit this file to add workspaces or MCPs, then run: ./launch.sh sync-config": None,
        "ollama_url": "http://host.docker.internal:11434",
        "request_timeout": 300,
        "mcp_fleet": mcp_fleet,
        "workspaces": workspaces,
    }

    # Build ordered output manually so comments and section order are readable
    out_lines: list[str] = [
        "# Portal 5 — single configuration source of truth",
        "# Edit this file to manage workspaces and MCP fleet.",
        "# Then run:  ./launch.sh sync-config",
        "# to regenerate:  config/backends.yaml workspace_routing, .mcp.json,",
        "#                 opencode.jsonc picker, imports/openwebui/workspaces/",
        "#",
        "# backends: block in backends.yaml is NOT generated — it is the operator's",
        "# hand-edited cluster scaling interface (CLAUDE.md Rule 1).",
        "",
        "ollama_url: \"http://host.docker.internal:11434\"",
        "request_timeout: 300",
        "",
        "# ── MCP Fleet ──────────────────────────────────────────────────────────────",
        "# expose_to_pipeline: true  → model-callable (included in tool_registry)",
        "# expose_to_ide: true       → available in Claude Code / opencode (.mcp.json)",
        "mcp_fleet:",
    ]

    for server in mcp_fleet:
        out_lines.append(f"  - id: {server['id']}")
        out_lines.append(f"    name: {server['name']}")
        if "port" in server:
            out_lines.append(f"    port: {server['port']}")
        out_lines.append(f"    expose_to_pipeline: {'true' if server['expose_to_pipeline'] else 'false'}")
        out_lines.append(f"    expose_to_ide: {'true' if server['expose_to_ide'] else 'false'}")
        if server.get("aliases"):
            out_lines.append(f"    aliases: {json.dumps(server['aliases'])}")
        if server.get("command"):
            cmd = server["command"]
            out_lines.append("    command:")
            out_lines.append(f"      type: {cmd['type']}")
            out_lines.append(f"      command: {json.dumps(cmd['command'])}")

    out_lines += [
        "",
        "# ── Workspace Catalog ──────────────────────────────────────────────────────",
        "# Keys must match workspace_routing in config/backends.yaml (generated by",
        "# sync-config — do not hand-edit workspace_routing after M1).",
        "#",
        "# expose_to_owui: true  → OWUI workspace preset is generated by sync-config.",
        "# enable_web_search:    → sets OWUI params.enable_web_search on the preset.",
        "# owui_system_prompt:   → sets OWUI params.system on the preset.",
        "workspaces:",
    ]

    # Emit each workspace as YAML using the block dumper for multiline strings
    for ws_id, entry in workspaces.items():
        ws_yaml = yaml.dump(
            {ws_id: entry},
            Dumper=_BlockDumper,
            default_flow_style=False,
            allow_unicode=True,
            width=120,
            sort_keys=False,
            indent=2,
        )
        # Re-indent from top-level to 2-space under workspaces:
        for line in ws_yaml.splitlines():
            out_lines.append("  " + line)

    portal_yaml_path = REPO / "config" / "portal.yaml"
    portal_yaml_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"\nWrote {portal_yaml_path}")
    print(f"  {len(workspaces)} workspaces, {len(mcp_fleet)} MCP servers")


if __name__ == "__main__":
    main()
