#!/usr/bin/env python3
"""Update workspace JSON files with appropriate toolIds."""

import json
from pathlib import Path

# Keyed by top-level workspace id — one entry per generated
# imports/openwebui/workspaces/workspace_*.json file (main() skips any id
# not in this map). Folded pre-collapse ids (auto-agentic, auto-redteam,
# auto-pentest, etc. — BUILD_PROGRAM_COLLAPSE_V1.md Phase 5/6) no longer have
# their own generated file (they're `?variant=` selections on auto-coding /
# auto-security), so their entries here were unreachable dead weight —
# removed rather than migrated (alias-retirement Phase 5; a canonical-form
# rename would just collide with the auto-coding/auto-security keys already
# present).
WORKSPACE_TOOLS = {
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
    "auto-bigfix": ["server:mcp:portal_code"],
    "auto-general-uncensored": ["server:mcp:portal_research"],
    "auto-extract-uncensored": ["server:mcp:portal_code"],
    "auto-cad": ["server:mcp:portal_code"],
    "auto-audio": ["server:mcp:portal_whisper"],
    "tools-specialist": ["server:mcp:portal_code", "server:mcp:portal_memory"],
}


def main() -> None:
    """Update workspace JSON files with current toolId mappings."""
    ws_dir = Path("imports/openwebui/workspaces")
    if not ws_dir.exists():
        # Try relative to script location
        ws_dir = Path(__file__).parent.parent / "imports/openwebui/workspaces"

    if not ws_dir.exists():
        print(f"WARNING: workspace directory not found: {ws_dir}")
        return

    errors = 0
    for ws_file in sorted(ws_dir.glob("workspace_*.json")):
        try:
            data = json.loads(ws_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"ERROR: {ws_file.name}: {e}")
            errors += 1
            continue

        ws_id = data.get("id", "")
        if ws_id not in WORKSPACE_TOOLS:
            print(f"SKIP: {ws_file.name} (id={ws_id!r} not in map)")
            continue

        tool_ids = WORKSPACE_TOOLS[ws_id]
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
    else:
        print("Done.")


if __name__ == "__main__":
    main()
