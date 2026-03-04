#!/usr/bin/env python3
"""Update workspace JSON files with appropriate toolIds."""
import json
from pathlib import Path

WORKSPACE_TOOLS = {
    "auto":           [],
    "auto-coding":    ["portal_code"],
    "auto-documents": ["portal_documents", "portal_code"],
    "auto-music":     ["portal_music", "portal_tts"],
    "auto-video":     ["portal_video", "portal_comfyui"],
    "auto-security":  ["portal_code"],
    "auto-redteam":   ["portal_code"],
    "auto-blueteam":  ["portal_code"],
    "auto-research":  [],
    "auto-reasoning": [],
    "auto-creative":  ["portal_tts"],
    "auto-vision":    ["portal_comfyui"],
    "auto-data":      ["portal_code", "portal_documents"],
}

ws_dir = Path("imports/openwebui/workspaces")
for ws_file in sorted(ws_dir.glob("workspace_*.json")):
    data = json.loads(ws_file.read_text())
    ws_id = data.get("id", "")
    if ws_id not in WORKSPACE_TOOLS:
        print(f"SKIP: {ws_file.name} (id={ws_id!r} not in map)")
        continue

    tool_ids = WORKSPACE_TOOLS[ws_id]
    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["toolIds"] = tool_ids
    ws_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated {ws_file.name}: toolIds={tool_ids}")

print("Done.")
