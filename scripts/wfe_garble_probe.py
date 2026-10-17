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
    a = ap.parse_args()
    req = json.loads(a.request.read_text())
    names = {t["function"]["name"] for t in req.get("tools") or []}
    cnt: collections.Counter = collections.Counter()
    for _ in range(a.n):
        found = corruption(*ask(a.engine, a.model, req), names)
        cnt.update(found or ["clean"])
    print(f"{a.engine} {a.model} n={a.n}: {dict(cnt)}")
    return 0 if set(cnt) == {"clean"} else 1


if __name__ == "__main__":
    sys.exit(main())
