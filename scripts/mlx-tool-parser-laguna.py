# Copyright © 2025 Apple Inc.
# Laguna (Poolside AI) tool call parser.
# Laguna uses JSON tool calls wrapped in <tool_call>...</tool_call> tags.

import json
from typing import Any

import regex as re

tool_call_start = "<tool_call>"
tool_call_end = "</tool_call>"

_tool_call_regex = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL
)


def parse_tool_call(text: str, tools: Any | None = None):
    match = _tool_call_regex.search(text)
    if match is None:
        raise ValueError(f"Could not parse tool call from: {text}")
    payload = json.loads(match.group(1))
    return dict(name=payload.get("name", ""), arguments=payload.get("arguments", {}))
