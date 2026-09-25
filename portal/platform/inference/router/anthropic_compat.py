"""Anthropic Messages API compatibility layer.

Converts between the Anthropic ``/v1/messages`` wire format and the
pipeline's internal OpenAI-compatible format, enabling Claude Code
(and any ``anthropic`` SDK client) to use Portal 5's local model fleet.

Usage
-----
Set in the environment before launching Claude Code::

    export ANTHROPIC_BASE_URL=http://localhost:9099
    export ANTHROPIC_API_KEY=$PIPELINE_API_KEY
    claude --model agenticheavy

Or use the wrapper script::

    scripts/cc-local.sh [--model <workspace-id>] [extra claude args]

Wire contract
-------------
Incoming Anthropic request → :func:`anthropic_to_openai_body` → OpenAI
body → existing pipeline routing + streaming → OpenAI SSE/JSON →
:func:`openai_stream_to_anthropic_sse` / :func:`openai_response_to_anthropic`
→ Anthropic SSE/JSON → Claude Code.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any


def anthropic_to_openai_body(body: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic Messages API request to OpenAI chat/completions format.

    Handles:
    - ``system`` string or content-block list → OpenAI system message
    - ``messages`` with text / tool_use / tool_result blocks
    - ``tools`` Anthropic format → OpenAI function definitions
    - ``max_tokens``, ``temperature``, ``top_p``, ``stop_sequences``
    """
    messages: list[dict[str, Any]] = []

    # System prompt
    system = body.get("system")
    if system:
        if isinstance(system, list):
            text = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
        else:
            text = str(system)
        if text.strip():
            messages.append({"role": "system", "content": text})

    for msg in body.get("messages", []):
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        # Content is a list of typed blocks
        text_parts: list[str] = []
        image_parts: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        # Every tool_result becomes its own tool message: Claude Code returns
        # parallel tool calls' results in ONE user message, and keeping only
        # the last left the backend with unanswered tool calls.
        tool_results: list[dict[str, Any]] = []

        for block in content:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "image":
                src = block.get("source") or {}
                if src.get("type") == "base64" and src.get("data"):
                    url = f"data:{src.get('media_type', 'image/png')};base64,{src['data']}"
                    image_parts.append({"type": "image_url", "image_url": {"url": url}})
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )
            elif btype == "tool_result":
                rc = block.get("content", "")
                if isinstance(rc, list):
                    rc = " ".join(b.get("text", "") for b in rc if b.get("type") == "text")
                text = str(rc)
                if block.get("is_error"):
                    text = f"Error: {text}"
                tool_results.append(
                    {"role": "tool", "tool_call_id": block.get("tool_use_id", ""), "content": text}
                )

        messages.extend(tool_results)
        if tool_calls:
            out: dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
            if text_parts:
                out["content"] = "\n".join(text_parts)
            messages.append(out)
        elif image_parts:
            parts: list[dict[str, Any]] = [{"type": "text", "text": t} for t in text_parts if t]
            messages.append({"role": role, "content": parts + image_parts})
        elif text_parts or not tool_results:
            # text that accompanies tool results follows them as its own turn
            messages.append({"role": role, "content": "\n".join(text_parts)})

    result: dict[str, Any] = {
        "model": body.get("model", "auto"),
        "messages": messages,
        "stream": body.get("stream", False),
    }

    for key, oai_key in (
        ("max_tokens", "max_tokens"),
        ("temperature", "temperature"),
        ("top_p", "top_p"),
    ):
        if key in body:
            result[oai_key] = body[key]

    if "stop_sequences" in body:
        result["stop"] = body["stop_sequences"]

    if "tools" in body:
        result["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in body["tools"]
        ]

    return result


def openai_response_to_anthropic(data: dict[str, Any], model_id: str) -> dict[str, Any]:
    """Convert a non-streaming OpenAI response to Anthropic Messages format."""
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message", {})
    content_text = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []
    usage = data.get("usage", {})

    content: list[dict[str, Any]] = []
    if content_text:
        content.append({"type": "text", "text": content_text})
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            inp = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            inp = {}
        content.append(
            {
                "type": "tool_use",
                "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                "name": fn.get("name", ""),
                "input": inp,
            }
        )

    finish = choice.get("finish_reason", "stop")
    # Anthropic's vocabulary: "length" is "max_tokens"; anything else unknown
    # to it (content_filter, ...) ends the turn.
    stop_reason = "tool_use" if tool_calls else ("max_tokens" if finish == "length" else "end_turn")

    return {
        "id": data.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model_id,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


async def openai_stream_to_anthropic_sse(
    line_iter: AsyncIterator[str],
    msg_id: str,
    model_id: str,
) -> AsyncIterator[str]:
    """Wrap an OpenAI SSE line iterator and yield Anthropic SSE event strings.

    Emits the full Anthropic streaming protocol:
    message_start → ping → per block (content_block_start →
    N×content_block_delta → content_block_stop) → message_delta → message_stop.
    Text becomes ``text`` blocks; tool-call deltas become ``tool_use`` blocks
    with ``input_json_delta`` (dropping them left Claude Code with
    ``stop_reason: tool_use`` and no tool to run). A pipeline error envelope
    becomes an ``error`` event.
    """

    def _evt(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    yield _evt(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model_id,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    yield _evt("ping", {"type": "ping"})

    output_tokens = 0
    stop_reason = "end_turn"
    block_index = -1
    open_block: str | None = None  # "text" | "tool:<openai index>"
    saw_tool = False

    def _stop_open() -> list[str]:
        nonlocal open_block
        if open_block is None:
            return []
        open_block = None
        return [_evt("content_block_stop", {"type": "content_block_stop", "index": block_index})]

    async for line in line_iter:
        if not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            break
        try:
            chunk = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue

        if chunk.get("error") and not chunk.get("choices"):
            err = chunk["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            for e in _stop_open():
                yield e
            yield _evt(
                "error",
                {"type": "error", "error": {"type": "api_error", "message": message}},
            )
            return

        if chunk.get("usage"):
            output_tokens = chunk["usage"].get("completion_tokens", output_tokens)

        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {})
        finish = choices[0].get("finish_reason")

        text = delta.get("content") or ""
        if text:
            if open_block != "text":
                for e in _stop_open():
                    yield e
                block_index += 1
                open_block = "text"
                yield _evt(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            yield _evt(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": "text_delta", "text": text},
                },
            )

        for i, tc in enumerate(delta.get("tool_calls") or []):
            key = f"tool:{tc.get('index', i)}"
            fn = tc.get("function") or {}
            if open_block != key:
                for e in _stop_open():
                    yield e
                block_index += 1
                open_block = key
                saw_tool = True
                yield _evt(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": block_index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                            "name": fn.get("name", ""),
                            "input": {},
                        },
                    },
                )
            args = fn.get("arguments")
            if args:
                yield _evt(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": block_index,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": args if isinstance(args, str) else json.dumps(args),
                        },
                    },
                )

        if finish:
            stop_reason = (
                "tool_use"
                if finish == "tool_calls" or saw_tool
                else ("max_tokens" if finish == "length" else "end_turn")
            )

    if block_index < 0:
        # Anthropic clients expect at least one content block.
        block_index, open_block = 0, "text"
        yield _evt(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        )
    for e in _stop_open():
        yield e
    yield _evt(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
    )
    yield _evt("message_stop", {"type": "message_stop"})
