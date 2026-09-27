from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from portal.modules.compliance.core.transport_dialects import _pipeline_api_key

ROOT = Path.cwd()
RUN_ID = "20260927T095336Z"
PRIVATE = ROOT / "portal/modules/compliance/data/private/stream_and_council_repair" / RUN_ID
BASE = "http://localhost:9099"
KEY = _pipeline_api_key()


def decode(raw: bytes) -> dict:
    content: list[str] = []
    reasoning = {"reasoning": [], "reasoning_content": [], "thinking": []}
    tool_names: list[str] = []
    finish: list[str] = []
    frames: list[dict] = []
    done_count = 0
    for data in _data_payloads(raw):
        if data == "[DONE]":
            done_count += 1
            continue
        frame = _parse_frame(data)
        if frame is None:
            continue
        frames.append(frame)
        for choice in frame.get("choices") or []:
            _capture_choice(choice, content, reasoning, tool_names, finish)
    assembled = "".join(content)
    all_reasoning = {k: "".join(v) for k, v in reasoning.items()}
    return {
        "frames": frames,
        "assembled_content": assembled,
        "reasoning": all_reasoning,
        "tool_names": tool_names,
        "finish_reasons": finish,
        "done_count": done_count,
    }


def _data_payloads(raw: bytes) -> list[str]:
    payloads = []
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    for block in text.split("\n\n"):
        data = "\n".join(
            line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
        )
        if data:
            payloads.append(data.strip())
    return payloads


def _parse_frame(data: str) -> dict | None:
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _capture_choice(
    choice: dict,
    content: list[str],
    reasoning: dict[str, list[str]],
    tool_names: list[str],
    finish: list[str],
) -> None:
    delta = choice.get("delta") or {}
    text = delta.get("content")
    if isinstance(text, str):
        content.append(text)
    _capture_reasoning(delta, reasoning)
    _capture_tool_names(delta, tool_names)
    if choice.get("finish_reason"):
        finish.append(str(choice["finish_reason"]))


def _capture_reasoning(delta: dict, reasoning: dict[str, list[str]]) -> None:
    for key in reasoning:
        value = delta.get(key)
        if isinstance(value, str) and value:
            reasoning[key].append(value)


def _capture_tool_names(delta: dict, tool_names: list[str]) -> None:
    for call in delta.get("tool_calls") or []:
        name = ((call.get("function") or {}).get("name") or "").strip()
        if name:
            tool_names.append(name)


def trace_for(correlation_id: str) -> tuple[int | None, bytes]:
    request = Request(
        f"{BASE}/v1/trace/{correlation_id}",
        headers={"Authorization": f"Bearer {KEY}"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed localhost
            return response.status, response.read()
    except Exception as exc:  # noqa: BLE001 - retained as an evidence outcome
        return getattr(exc, "code", None), str(exc).encode()


def _capture_stream(label: str, use_tool: bool) -> tuple[bytes, int | None, str, str, float]:
    message = (
        "Call compliance_context for ref CIP-007-6 R2 Part 2.3 with mode material. "
        "After the tool returns, reply exactly STREAM_P0_TOOL_SENTINEL."
        if use_tool
        else "Reply exactly STREAM_P0_NO_TOOL_SENTINEL and no other text."
    )
    body = {
        "model": "compliance-reading",
        "messages": [{"role": "user", "content": message}],
        "stream": True,
        "max_tokens": 512,
    }
    if use_tool:
        body["tool_choice"] = {"type": "function", "function": {"name": "compliance_context"}}
    else:
        body["portal_no_tools"] = True
    correlation_id = f"stream-repair-p0-{RUN_ID}-{label}"
    payload = json.dumps(body).encode()
    request = Request(
        f"{BASE}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KEY}",
            "X-Correlation-ID": correlation_id,
        },
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=900) as response:  # noqa: S310 - fixed localhost
            raw = response.read()
            status = response.status
            route = response.headers.get("x-portal-route", "")
            response_correlation_id = response.headers.get("x-correlation-id", correlation_id)
    except Exception as exc:  # noqa: BLE001 - keep failed live attempts attributable
        raw = str(exc).encode()
        status = getattr(exc, "code", None)
        route = (
            getattr(exc, "headers", {}).get("x-portal-route", "")
            if getattr(exc, "headers", None)
            else ""
        )
        response_correlation_id = correlation_id
    return raw, status, route, response_correlation_id, round(time.monotonic() - started, 3)


def run(label: str, use_tool: bool) -> dict:
    raw, status, route, response_correlation_id, elapsed = _capture_stream(label, use_tool)
    raw_path = PRIVATE / f"{label}.raw.sse"
    raw_path.write_bytes(raw)
    raw_path.chmod(0o600)
    decoded = decode(raw)
    trace_status, trace_raw = trace_for(response_correlation_id)
    trace_path = PRIVATE / f"{label}.trace.json"
    trace_path.write_bytes(trace_raw)
    trace_path.chmod(0o600)
    if trace_status == 200:
        try:
            trace = json.loads(trace_raw)
        except json.JSONDecodeError:
            trace = {}
    else:
        trace = {}
    spans = trace.get("spans") or []
    result = {
        "label": label,
        "requested_route": "compliance-reading",
        "use_tool": use_tool,
        "http_status": status,
        "route_header": route,
        "correlation_id": response_correlation_id,
        "duration_seconds": elapsed,
        "raw_sse_path": str(raw_path),
        "raw_sse_sha256": hashlib.sha256(raw).hexdigest(),
        "trace_http_status": trace_status,
        "trace_path": str(trace_path),
        "assembled_content_private": decoded["assembled_content"],
        "leading_crlf_count": len(decoded["assembled_content"])
        - len(decoded["assembled_content"].lstrip("\r\n")),
        "reasoning_lengths": {k: len(v) for k, v in decoded["reasoning"].items()},
        "reasoning_sha256": {
            k: hashlib.sha256(v.encode()).hexdigest() for k, v in decoded["reasoning"].items()
        },
        "tool_names": decoded["tool_names"],
        "finish_reasons": decoded["finish_reasons"],
        "done_count": decoded["done_count"],
        "trace_outcome": trace.get("outcome"),
        "trace_span_names": [s.get("name") for s in spans if isinstance(s, dict)],
    }
    decoded_path = PRIVATE / f"{label}.decoded.private.json"
    decoded_path.write_text(json.dumps(decoded, ensure_ascii=False, indent=2) + "\n")
    decoded_path.chmod(0o600)
    public = {k: v for k, v in result.items() if k != "assembled_content_private"}
    public["at_utc"] = datetime.now(UTC).isoformat()
    print(json.dumps(public, sort_keys=True))
    return public


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="omlx", help="capture label prefix, such as ollama")
    args = parser.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    for label, tool in ((f"{args.prefix}_no_tool", False), (f"{args.prefix}_tool", True)):
        run(label, tool)
