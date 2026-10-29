#!/usr/bin/env python3
"""Check an Ollama model's tool round-trip with thinking enabled and disabled."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TOOL = {
    "type": "function",
    "function": {
        "name": "probe_lookup",
        "description": "Return a fixed probe status.",
        "parameters": {
            "type": "object",
            "properties": {"lookup_id": {"type": "string"}},
            "required": ["lookup_id"],
        },
    },
}
LOOKUP_ID = "CASE-42"
TOOL_RESULT = {"lookup_id": LOOKUP_ID, "status": "ready"}


def chat(
    host: str,
    model: str,
    think: bool,
    messages: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": [TOOL],
        "think": think,
        "stream": False,
    }
    request = Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama chat request failed: {exc}") from exc


def assert_thinking(message: dict[str, Any], think: bool) -> None:
    thinking = message.get("thinking") or ""
    content = message.get("content") or ""
    if think and not thinking:
        raise RuntimeError("think=true returned no parsed thinking content")
    if not think and (thinking or "<think>" in content or "</think>" in content):
        raise RuntimeError("think=false leaked thinking content or tags")


def run_mode(host: str, model: str, think: bool, timeout: float) -> None:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Call probe_lookup exactly once with lookup_id CASE-42. "
                "After its result, answer with the returned status and do not call a tool again."
            ),
        },
        {"role": "user", "content": "Look up CASE-42 and report its status."},
    ]
    first = chat(host, model, think, messages, timeout).get("message", {})
    assert_thinking(first, think)
    calls = first.get("tool_calls") or []
    if len(calls) != 1:
        raise RuntimeError(f"expected one structured tool call, got {len(calls)}")
    function = calls[0].get("function", {})
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if function.get("name") != TOOL["function"]["name"]:
        raise RuntimeError("model called the wrong tool")
    if arguments.get("lookup_id") != LOOKUP_ID:
        raise RuntimeError("model sent the wrong lookup_id")

    assistant_message = {
        "role": "assistant",
        "content": first.get("content") or "",
        "tool_calls": calls,
    }
    if first.get("thinking"):
        assistant_message["thinking"] = first["thinking"]
    messages.extend(
        [
            assistant_message,
            {
                "role": "tool",
                "tool_name": TOOL["function"]["name"],
                "content": json.dumps(TOOL_RESULT),
            },
        ]
    )

    final = chat(host, model, think, messages, timeout).get("message", {})
    assert_thinking(final, think)
    if final.get("tool_calls"):
        raise RuntimeError("model called a tool again after receiving its result")
    content = final.get("content") or ""
    if TOOL_RESULT["status"] not in content.casefold():
        raise RuntimeError("final answer did not include the tool result")
    print(
        f"think={str(think).lower()}: tool call and result turn passed; final_chars={len(content)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="Ollama model name created from a Modelfile")
    parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    )
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    for think in (False, True):
        run_mode(args.host, args.model, think, args.timeout)


if __name__ == "__main__":
    main()
