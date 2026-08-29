#!/usr/bin/env python3
"""Compute OWUI toolIds from config/portal.yaml's tools: lists — single source
of truth, no hand-maintained per-workspace toolId list to drift out of sync.

Ground truth for TOOL_TO_SERVER was verified against each MCP module's
@mcp.tool() definitions directly (not inferred from a workspace's tools list),
so a workspace/persona under- or over-declaring tools shows up as a real gap
instead of being silently copied forward.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Raw MCP tool function name -> OWUI Tool Server id (server:mcp:<id>).
# Verified against each module's @mcp.tool()-decorated function names:
#   portal/modules/coding/tools/code_sandbox_mcp.py    -> portal_code
#   portal/modules/documents/tools/document_mcp.py     -> portal_documents
#   portal/modules/media/tools/whisper_mcp.py          -> portal_whisper
#   portal/modules/media/tools/tts_mcp.py              -> portal_tts
#   portal/modules/media/tools/music_minimax_mcp.py    -> portal_music_minimax
#   portal/modules/media/tools/music_ace_mcp.py        -> portal_music_ace
#   portal/modules/media/tools/mflux_mcp.py            -> portal_mflux
#   portal/modules/media/tools/video_mlx_mcp.py        -> portal_video_mlx
#   portal/modules/security/tools/security_mcp.py      -> portal_security
#   portal/platform/memory/memory_mcp.py               -> portal_memory
#   portal/modules/research/tools/web_search_mcp.py    -> portal_research
#   portal/modules/research/tools/rag_mcp.py           -> portal_rag
#   portal/modules/research/tools/browser_mcp.py       -> portal_browser
#   portal/modules/cad/tools/cad_render_mcp.py         -> portal_cad
TOOL_TO_SERVER: dict[str, str] = {
    # portal_code
    "execute_bash": "portal_code",
    "execute_nodejs": "portal_code",
    "execute_powershell": "portal_code",
    "execute_python": "portal_code",
    "sandbox_status": "portal_code",
    # portal_documents
    "create_word_document": "portal_documents",
    "create_powerpoint": "portal_documents",
    "create_excel": "portal_documents",
    "convert_document": "portal_documents",
    "list_generated_files": "portal_documents",
    "read_word_document": "portal_documents",
    "read_excel": "portal_documents",
    "read_powerpoint": "portal_documents",
    "read_pdf": "portal_documents",
    # portal_whisper
    "transcribe_audio": "portal_whisper",
    "transcribe_with_speakers": "portal_whisper",
    # portal_tts
    "speak": "portal_tts",
    "clone_voice": "portal_tts",
    "register_voice": "portal_tts",
    "list_voices": "portal_tts",
    "minimax_generate": "portal_music_minimax",
    "minimax_status": "portal_music_minimax",
    "minimax_models": "portal_music_minimax",
    # portal_music_ace — DEAD: disabled 2026-08-27 after TASK_MUSIC_DUAL_BACKEND's
    # [GATE: SELECT ENGINE] (operator picked MiniMax; see config/portal.yaml's
    # mcp_fleet comment for the full rationale). Kept mapped so a stale
    # workspace/persona reference is recognized, not silently dropped as
    # unknown; DEAD_SERVERS below excludes it from any computed toolIds.
    "ace_generate": "portal_music_ace",
    "ace_status": "portal_music_ace",
    "ace_models": "portal_music_ace",
    # portal_mflux — MLX-native image generation (mflux_mcp.py, :8933).
    "generate_image": "portal_mflux",
    "edit_image": "portal_mflux",
    # portal_video_mlx — MLX-native video generation (video_mlx_mcp.py, :8935).
    # The `video` module is off by default, so portal_video_mlx is listed in
    # DEAD_SERVERS until an operator enables it — a stale `generate_video`
    # reference is then recognized, not dropped as unknown.
    "generate_video": "portal_video_mlx",
    "animate_image": "portal_video_mlx",
    # portal_security
    "classify_vulnerability": "portal_security",
    "lab_perception": "portal_security",
    # portal_memory
    "remember": "portal_memory",
    "recall": "portal_memory",
    "forget": "portal_memory",
    "list_memories": "portal_memory",
    "clear_memories": "portal_memory",
    # portal_research (web_search_mcp.py — distinct server from portal_rag
    # below, despite both living under modules/research/)
    "web_search": "portal_research",
    "web_fetch": "portal_research",
    "news_search": "portal_research",
    # portal_rag (rag_mcp.py)
    "kb_search": "portal_rag",
    "kb_list": "portal_rag",
    "kb_search_all": "portal_rag",
    "kb_ingest": "portal_rag",
    "kb_optimize": "portal_rag",
    "kb_restore": "portal_rag",
    "kb_versions": "portal_rag",
    # portal_browser
    "browser_navigate": "portal_browser",
    "browser_snapshot": "portal_browser",
    "browser_click": "portal_browser",
    "browser_fill": "portal_browser",
    "browser_screenshot": "portal_browser",
    "browser_evaluate": "portal_browser",
    "browser_close": "portal_browser",
    "browser_list_profiles": "portal_browser",
    # portal_cad
    "render_mesh": "portal_cad",
    "render_openscad": "portal_cad",
    "convert_cad": "portal_cad",
}

# Server ids with no live backing service right now — a tool that maps here
# contributes no toolId (the workspace/persona keeps its other, working tools;
# this one just won't show as active in OWUI's UI, matching reality).
DEAD_SERVERS: frozenset[str] = frozenset({"portal_video_mlx", "portal_music_ace"})

# Host-native pipeline tools with no MCP server / OWUI toolId by design
# (portal/platform/inference router_pipe.py handles these directly, not via
# an MCP Tool Server) — not a gap, just excluded from toolIds intentionally.
NO_SERVER_TOOLS: frozenset[str] = frozenset(
    {"explore_repository", "read_text_file", "list_directory", "search_files", "write_file"}
)


def compute_tool_ids(tools: list[str]) -> list[str]:
    """Map raw tool names to sorted, deduped OWUI toolIds, dropping dead/unmapped ones."""
    ids: set[str] = set()
    for t in tools:
        server = TOOL_TO_SERVER.get(t)
        if server and server not in DEAD_SERVERS:
            ids.add(f"server:mcp:{server}")
    return sorted(ids)


def all_tools_dead(tools: list[str]) -> bool:
    """True if every declared tool maps to a dead server or nothing at all —
    i.e. this workspace/persona has zero working tools despite declaring some."""
    if not tools:
        return False
    return all(
        TOOL_TO_SERVER.get(t) is None or TOOL_TO_SERVER.get(t) in DEAD_SERVERS for t in tools
    )


def _portal_yaml_path() -> Path:
    for candidate in (Path("/config/portal.yaml"), Path("config/portal.yaml")):
        if candidate.exists():
            return candidate
    # Try relative to script location (host `uv run` invocation)
    return Path(__file__).parent.parent / "config" / "portal.yaml"


def load_workspace_raw_tools() -> dict[str, list[str]]:
    """{workspace_id: raw tools list} for every base workspace in portal.yaml
    (variants excluded — OWUI presets are one per base workspace id; a variant
    is selected via ?variant= at request time, not a separate preset)."""
    cfg = yaml.safe_load(_portal_yaml_path().read_text())
    return {ws_id: (spec.get("tools") or []) for ws_id, spec in cfg.get("workspaces", {}).items()}


def main() -> int:
    """Update workspace JSON files with current toolId mappings."""
    ws_dir = Path("imports/openwebui/workspaces")
    if not ws_dir.exists():
        ws_dir = Path(__file__).parent.parent / "imports/openwebui/workspaces"

    if not ws_dir.exists():
        print(f"WARNING: workspace directory not found: {ws_dir}")
        return 1

    raw_tools_by_ws = load_workspace_raw_tools()

    errors = 0
    for ws_file in sorted(ws_dir.glob("workspace_*.json")):
        try:
            data = json.loads(ws_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR: {ws_file.name}: {e}")
            errors += 1
            continue

        ws_id = data.get("id", "")
        if ws_id not in raw_tools_by_ws:
            print(f"SKIP: {ws_file.name} (id={ws_id!r} not in config/portal.yaml)")
            continue

        tool_ids = compute_tool_ids(raw_tools_by_ws[ws_id])
        if "meta" not in data:
            data["meta"] = {}
        if data["meta"].get("toolIds") == tool_ids:
            continue  # already current
        data["meta"]["toolIds"] = tool_ids
        try:
            ws_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"Updated {ws_file.name}: toolIds={tool_ids}")
        except OSError as e:
            print(f"ERROR writing {ws_file.name}: {e}")
            errors += 1

    if errors:
        print(f"Done with {errors} error(s).")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
