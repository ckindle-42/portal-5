#!/usr/bin/env python3
"""Tool calling through the real dispatch path (TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §B5).

Per P5-TOOL-001: support is never inferred from a model card — direct probe
only. The tool schema is REAL, taken from the live compliance MCP's
tools/list (the schema the reading workspace dispatches), and the probe
verifies, per engine:

  1. a well-formed tool_calls entry (name + arguments present),
  2. arguments that parse as JSON,
  3. THE SERIALIZED BYTES — exact repr of the arguments string, because tool-
     argument SERIALIZATION failure (not model capability) was the actual
     root cause of Hunter non-convergence,
  4. behaviour under stream:true (deltas must assemble into the same call),
  5. behaviour non-streaming.

Usage:
    SPLASH_API_KEY=... uv run python scripts/prove_then_scale/b5_tool_probe.py \
        --engine splash --model incoai/Qwen3.8-27B-Splash
    uv run python scripts/prove_then_scale/b5_tool_probe.py --engine ollama --model <tag>
    uv run python scripts/prove_then_scale/b5_tool_probe.py --engine omlx --model <dir>
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
ART = REPO_ROOT / "reports" / "compliance" / "prove_then_scale" / "b5"

ENGINES = {
    "ollama": "http://localhost:11434",
    "omlx": "http://localhost:8085",
    "splash": os.environ.get("BENCH_SPLASH_URL", "http://localhost:8086"),
}

QUESTION = (
    "What is in scope for CIP-007-6 R2 Part 2.2? Use the provided tool to fetch "
    "the section index for that requirement."
)


def fetch_real_schema() -> dict:
    """tools/list from the LIVE compliance MCP (streamable HTTP)."""
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "b5-tool-probe", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as c:
        r = c.post("http://localhost:8937/mcp", json=init, headers=headers)
        session = r.headers.get("mcp-session-id", "")
        h2 = {**headers, "mcp-session-id": session}
        c.post(
            "http://localhost:8937/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=h2,
        )
        r = c.post(
            "http://localhost:8937/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=h2,
        )
        text = r.text
        payload = None
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                break
        if payload is None:
            payload = json.loads(text)
    tools = payload["result"]["tools"]
    tool = next(t for t in tools if t["name"] == "compliance_context")
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": (tool.get("description") or "")[:800],
            "parameters": tool["inputSchema"],
        },
    }


def assembled_tool_calls(parts: list[dict]) -> list[dict]:
    by_index: dict[int, dict] = {}
    for p in parts:
        for tc in p:
            idx = tc.get("index", 0)
            slot = by_index.setdefault(idx, {"id": "", "name": "", "args": ""})
            fn = tc.get("function") or {}
            slot["id"] = slot["id"] or tc.get("id", "")
            slot["name"] += fn.get("name") or ""
            slot["args"] += fn.get("arguments") or ""
    return [by_index[k] for k in sorted(by_index)]


def _probe_nonstream(engine: str, model: str, headers: dict, body: dict, out: dict) -> None:
    r = httpx.post(
        f"{ENGINES[engine]}/v1/chat/completions", json=body, headers=headers, timeout=900.0
    )
    out["nonstream_status"] = r.status_code
    if r.status_code != 200:
        out["nonstream_error"] = r.text[:400]
        return
    msg = r.json()["choices"][0].get("message") or {}
    tcs = msg.get("tool_calls") or []
    out["nonstream_tool_calls"] = len(tcs)
    if not tcs:
        return
    args_str = tcs[0]["function"].get("arguments") or ""
    out["nonstream_tool_name"] = tcs[0]["function"].get("name")
    try:
        parsed = json.loads(args_str)
        out["nonstream_args_parse"] = "OK"
        out["nonstream_args_ref"] = parsed.get("ref", "")
    except json.JSONDecodeError as exc:
        out["nonstream_args_parse"] = f"FAIL: {exc}"
    # THE SERIALIZED BYTES — the Hunter root cause check
    out["nonstream_args_bytes_repr"] = repr(args_str[:300])
    out["nonstream_args_len"] = len(args_str)


def _probe_stream(engine: str, headers: dict, body: dict, out: dict) -> None:
    body_stream = {**body, "stream": True}
    parts: list[dict] = []
    content_chars = 0
    with httpx.stream(
        "POST",
        f"{ENGINES[engine]}/v1/chat/completions",
        json=body_stream,
        headers=headers,
        timeout=900.0,
    ) as rs:
        out["stream_status"] = rs.status_code
        if rs.status_code != 200:
            return
        for line in rs.iter_lines():
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if payload_text == "[DONE]":
                break
            try:
                chunk = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                content_chars += len(delta["content"])
            if delta.get("tool_calls"):
                parts.append(delta["tool_calls"])
    out["stream_tool_calls"] = len(parts)
    if parts:
        joined = assembled_tool_calls(parts)
        out["stream_assembled_name"] = joined[0]["name"]
        out["stream_assembled_args_len"] = len(joined[0]["args"])
        try:
            json.loads(joined[0]["args"])
            out["stream_args_parse"] = "OK"
        except json.JSONDecodeError as exc:
            out["stream_args_parse"] = f"FAIL: {exc}"
        out["stream_assembled_bytes_repr"] = repr(joined[0]["args"][:300])
    out["stream_content_chars"] = content_chars


def probe(engine: str, model: str) -> dict:
    base = ENGINES[engine]
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("SPLASH_API_KEY")
    if key and engine == "splash":
        headers["Authorization"] = f"Bearer {key}"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": QUESTION}],
        "tools": [SCHEMA],
        "max_tokens": 512,
        "temperature": 0.0,
    }
    if engine == "splash":
        body["reasoning_effort"] = "none"
    else:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    out: dict = {"engine": engine, "model": model}
    _probe_nonstream(engine, model, headers, body, out)
    _probe_stream(engine, headers, body, out)
    return out


SCHEMA: dict = {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=sorted(ENGINES))
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.engine == "splash" and not os.environ.get("SPLASH_API_KEY"):
        print("SPLASH_API_KEY missing")
        return 1
    global SCHEMA
    if not SCHEMA:
        SCHEMA = fetch_real_schema()
        print(
            f"real schema fetched: {SCHEMA['function']['name']} ({len(SCHEMA['function']['parameters'].get('properties', {}))} params)"
        )
    ART.mkdir(parents=True, exist_ok=True)
    result = probe(args.engine, args.model)
    result["recorded_at"] = datetime.now(UTC).isoformat()
    out = ART / f"toolprobe_{args.engine}_{args.model.replace('/', '_')}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
