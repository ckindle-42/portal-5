"""Standalone CLI probe for the tool preselector — Phase 2 POC gate (§4.5).

Exercises preselect() directly against a live Ollama call, without any
pipeline/tool_registry wiring, so a candidate model's raw ranking
quality can be sanity-checked in isolation.

Usage:
    python3 -m portal.platform.inference.tool_preselect.cli_probe \\
        --model "hf.co/openbmb/MiniCPM5-1B-GGUF:Q4_K_M" \\
        --tools "execute_bash,execute_python,web_search,read_text_file,write_file,remember,recall,query_splunk,create_word_document,render_openscad" \\
        --user-turn "please look up when the last stock market crash was" \\
        --k 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

# Short, illustrative descriptions for common Portal tool names — this probe
# runs standalone (no live tool_registry/MCP discovery), so it needs its own
# lightweight lookup. Unknown names fall back to an empty description; the
# model still has the tool name itself to rank against.
_KNOWN_DESCRIPTIONS: dict[str, str] = {
    "execute_bash": "Run a bash command in an isolated sandbox container",
    "execute_python": "Run Python code in an isolated sandbox container",
    "execute_nodejs": "Run Node.js code in an isolated sandbox container",
    "web_search": "Search the web for current information via SearXNG",
    "read_text_file": "Read the contents of a text file from disk",
    "write_file": "Write content to a file on disk",
    "remember": "Store a fact in cross-session memory",
    "recall": "Retrieve previously stored facts from cross-session memory",
    "query_splunk": "Search Splunk SPL detection library and query syntax",
    "create_word_document": "Generate a Word (.docx) document",
    "create_excel": "Generate an Excel (.xlsx) spreadsheet",
    "create_powerpoint": "Generate a PowerPoint (.pptx) presentation",
    "render_openscad": "Render an OpenSCAD 3D CAD model to an image or STL",
    "speak": "Convert text to speech audio",
    "transcribe_audio": "Transcribe an audio file to text",
    "generate_music": "Generate a music clip from a text prompt",
    "browser_navigate": "Navigate a headless browser to a URL",
    "browser_screenshot": "Take a screenshot of the current browser page",
}


async def _run(args: argparse.Namespace) -> int:
    from portal.platform.inference.tool_preselect.parser import (
        indices_to_tool_names,
        parse_ranked_indices,
    )
    from portal.platform.inference.tool_preselect.prompts import build_prompt

    tool_names = [t.strip() for t in args.tools.split(",") if t.strip()]
    descriptions = {n: _KNOWN_DESCRIPTIONS.get(n, "") for n in tool_names}

    prompt = build_prompt(args.user_turn, tool_names, descriptions, args.k, slack=3)

    import httpx

    payload = {
        "model": args.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.0, "top_p": 1.0, "top_k": 1, "num_predict": 200},
    }

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{args.ollama_url}/api/generate", json=payload)
    latency_ms = int((time.monotonic() - t0) * 1000)
    resp.raise_for_status()
    raw = resp.json().get("response", "")

    indices = parse_ranked_indices(raw, valid_max=len(tool_names))
    ranked = indices_to_tool_names(indices, tool_names)

    result = {
        "model": args.model,
        "user_turn": args.user_turn,
        "k": args.k,
        "ranked_tools": ranked[: args.k],
        "raw_ranked_all": ranked,
        "latency_ms": latency_ms,
        "raw_response": raw,
    }
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Tool preselector CLI probe")
    p.add_argument("--model", required=True, help="Ollama model tag for the preselector")
    p.add_argument("--tools", required=True, help="Comma-separated tool names")
    p.add_argument("--user-turn", required=True, help="Simulated user turn text")
    p.add_argument("--k", type=int, default=3, help="Top-K to report")
    p.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")
    args = p.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
