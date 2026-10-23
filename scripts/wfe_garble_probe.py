#!/usr/bin/env python3
"""Replay one captured chat request against an engine N times and count output corruption:
zero-width spaces (U+200B), tool names not in the request's tools, and '..' inside arguments.

Found 2026-10-17: oMLX's granite-4.1-8b-mxfp8 conversion put U+200B inside paths whenever tools
were in the request (10/10), where the Ollama GGUF and granite-4.1-30b-4bit were clean. Capture a
request by pointing the pipeline's OMLX_URL at a logging proxy; this is a direct-engine
DIAGNOSTIC, never row evidence.

    uv run python scripts/wfe_garble_probe.py tests/wfe/fixtures/granite8b_mxfp8_zwsp_hop2_request.json \
        --engine omlx --model granite-4.1-8b-mxfp8 -n 10
    uv run python scripts/wfe_garble_probe.py <request.json> --engine ollama --model granite4.1:8b-ctx16k
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from pathlib import Path

ZWSP = "​"


def corruption(content: str, calls: list[dict], tool_names: set[str]) -> list[str]:
    """The kinds of corruption in one reply (empty = clean)."""
    found = []
    if ZWSP in content:
        found.append("zwsp-text")
    for c in calls:
        if ZWSP in json.dumps(c.get("arguments"), ensure_ascii=False):
            found.append("zwsp-args")
        if tool_names and c.get("name") not in tool_names:
            found.append(f"bad-name:{c.get('name')!r}")
        if ".." in json.dumps(c.get("arguments")):
            found.append("dotdot-args")
    return found


def _server_tools(port: object) -> list[dict]:
    """Native tools/list for one fleet port, else its REST /tools manifest."""
    import asyncio

    import httpx

    from portal.platform.inference.mcp_http import list_tools

    if not isinstance(port, int):
        return []
    base = f"http://localhost:{port}"

    async def fetch() -> list[dict]:
        async with httpx.AsyncClient() as client:
            return await list_tools(client, base, 3.0)

    try:
        return asyncio.run(fetch())
    except Exception:  # noqa: BLE001
        pass
    try:
        with urllib.request.urlopen(f"{base}/tools", timeout=3) as response:  # noqa: S310
            payload = json.load(response)
    except Exception:  # noqa: BLE001
        return []
    tools = payload.get("tools", []) if isinstance(payload, dict) else []
    return [tool for tool in tools if isinstance(tool, dict)]


def workspace_tools(workspace: str) -> list[dict]:
    """The OpenAI function schemas a workspace offers, from its `tools` and the MCP manifests."""
    import yaml

    root = Path(__file__).resolve().parents[1]
    names = (
        yaml.safe_load((root / "config/portal.yaml").read_text())["workspaces"][workspace].get(
            "tools"
        )
        or []
    )
    schemas = {}
    for f in (root / "config/inference").glob("*manifest*.json"):
        data = json.loads(f.read_text())
        for t in data if isinstance(data, list) else data.get("tools", []):
            if isinstance(t, dict) and "name" in t and "parameters" in t:
                schemas[t["name"]] = t
    if missing := [n for n in names if n not in schemas]:  # an MCP with no manifest file
        for e in yaml.safe_load((root / "config/portal.yaml").read_text())["mcp_fleet"]:
            for t in _server_tools(e.get("port")):
                params = t.get("parameters") or t.get("inputSchema")
                if t.get("name") in missing and params:
                    schemas[t["name"]] = {**t, "parameters": params}
    return [
        {
            "type": "function",
            "function": {
                "name": n,
                "description": schemas[n].get("description", ""),
                "parameters": schemas[n]["parameters"],
            },
        }
        for n in names
        if n in schemas
    ]


def ask(engine: str, model: str, req: dict) -> tuple[str, list[dict]]:
    body = {k: v for k, v in req.items() if k not in ("exec_audit", "stream_options")}
    body["model"], body["stream"] = model, False
    if engine == "ollama":
        msgs = []
        for m in body["messages"]:
            m = dict(m)
            if m.get("tool_calls"):
                m["tool_calls"] = [
                    {
                        "function": {
                            "name": c["function"]["name"],
                            "arguments": json.loads(c["function"]["arguments"]),
                        }
                    }
                    for c in m["tool_calls"]
                ]
            msgs.append(m)
        options = {"temperature": body.get("temperature", 0), "num_predict": 400}
        data = {
            "model": model,
            "messages": msgs,
            "tools": body.get("tools"),
            "stream": False,
            "options": options,
        }
        url, headers = "http://localhost:11434/api/chat", {}
    else:
        from portal.platform.inference.omlx_auth import omlx_headers

        data, url, headers = body, "http://localhost:8085/v1/chat/completions", omlx_headers()
    r = urllib.request.Request(
        url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", **headers}
    )
    with urllib.request.urlopen(r, timeout=600) as resp:  # noqa: S310
        out = json.load(resp)
    m = out["message"] if engine == "ollama" else out["choices"][0]["message"]
    calls = [
        {"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
        for c in m.get("tool_calls") or []
    ]
    return m.get("content") or "", calls


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("request", type=Path)
    ap.add_argument("--engine", choices=("omlx", "ollama"), required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--workspace", help="replace the request's tools with this workspace's tools")
    ap.add_argument("--no-tools", action="store_true", help="drop the tools (control)")
    a = ap.parse_args()
    req = json.loads(a.request.read_text())
    if a.workspace:
        req["tools"] = workspace_tools(a.workspace)
    if a.no_tools:
        req.pop("tools", None)
        req.pop("tool_choice", None)
    names = {t["function"]["name"] for t in req.get("tools") or []}  # after any swap
    cnt: collections.Counter = collections.Counter()
    for _ in range(a.n):
        found = corruption(*ask(a.engine, a.model, req), names)
        cnt.update(found or ["clean"])
    label = (
        f"workspace={a.workspace} ({len(req.get('tools') or [])} tools)"
        if a.workspace
        else ("no tools" if a.no_tools else "request tools")
    )
    print(f"{a.engine} {a.model} n={a.n} {label}: {dict(cnt)}")
    return 0 if set(cnt) == {"clean"} else 1


if __name__ == "__main__":
    sys.exit(main())
