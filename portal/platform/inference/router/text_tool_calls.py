"""Recover tool calls a model wrote into ``content`` instead of ``tool_calls``.

Dependency-free on purpose: the pipeline's tool loops and the WFE harness
(which must score exactly what the pipeline delivers) both import it.
"""

from __future__ import annotations

import json
import re
from typing import Any

# P5-OMLX-QWEN3CODER-TOOLTEXT-001: Qwen3-Coder sometimes writes a stray word
# and skips the <tool_call> opener, e.g. "Paris\n<function=get_weather>
# <parameter=city>\nParis\n</parameter>\n</function>\n</tool_call>". oMLX's
# parser only enters tool mode on the opener, so the call arrives as plain
# content. These helpers recover such calls when tools were offered.
TEXT_TOOL_CALL_MARKERS = ("<tool_call>", "<function=")
_TOOL_CALL_WRAPPER_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
_XML_FUNCTION_RE = re.compile(r"<function=([^>\s]+)>(.*?)</function>", re.DOTALL)
_XML_PARAMETER_RE = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)


def _xml_param_value(raw: str, schema: dict[str, Any]) -> Any:
    """Convert one ``<parameter>`` body using the tool schema's declared type."""
    value = raw[1:] if raw.startswith("\n") else raw
    value = value[:-1] if value.endswith("\n") else value
    if schema.get("type", "string") == "string":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _decode_json_call(raw_payload: str) -> tuple[str, dict[str, Any]] | None:
    try:
        payload, end = json.JSONDecoder().raw_decode(raw_payload)
    except json.JSONDecodeError:
        return None
    # The live Granite/oMLX path was observed to append one unmatched closing
    # brace after an otherwise valid wrapped call. Accept only that single
    # terminal character; other trailing content remains an unparsed answer.
    if raw_payload[end:].strip() not in ("", "}") or not isinstance(payload, dict):
        return None
    function = payload.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments", {})
    else:
        name = payload.get("name")
        arguments = payload.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return None
    return name, arguments


def salvage_text_tool_calls(
    content: str, tools: list[dict[str, Any]] | None
) -> tuple[str, list[dict[str, Any]]]:
    """Recover JSON or XML tool calls written into ``content``.

    Only calls naming an offered tool count; anything else returns no calls so
    the text is delivered unchanged. Returns ``(text_before_the_call, calls)``
    with calls in OpenAI ``tool_calls`` shape (arguments as a JSON string).
    """
    offered = {
        (t.get("function") or {}).get("name"): (t.get("function") or {}).get("parameters") or {}
        for t in tools or []
    }
    text = content or ""
    matches: list[tuple[int, str, dict[str, Any]]] = []
    for match in _TOOL_CALL_WRAPPER_RE.finditer(text):
        raw_payload = match.group(1).strip()
        if not raw_payload.startswith("{"):
            continue  # The legacy <function=name> form is parsed below.
        decoded = _decode_json_call(raw_payload)
        if decoded is None:
            return content, []
        name, arguments = decoded
        matches.append((match.start(), name, arguments))

    for match in _XML_FUNCTION_RE.finditer(text):
        name = match.group(1)
        props = offered.get(name, {}).get("properties") or {}
        arguments = {
            key: _xml_param_value(raw, props.get(key) or {})
            for key, raw in _XML_PARAMETER_RE.findall(match.group(2))
        }
        matches.append((match.start(), name, arguments))

    if not matches or any(name not in offered for _, name, _ in matches):
        return content, []
    matches.sort(key=lambda item: item[0])
    calls: list[dict[str, Any]] = []
    for i, (_start, name, args) in enumerate(matches):
        calls.append(
            {
                "id": f"call_text_{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        )
    prefix = text[: matches[0][0]].replace("<tool_call>", "").strip()
    return prefix, calls


class TextToolCallHoldback:
    """Stream filter that withholds content from the first tool-call marker on.

    ``feed`` returns the text that is safe to show now. A trailing fragment
    that could still become a marker (``"<func"``) is kept back until the next
    chunk decides it. Once a marker is seen everything after it is held for
    :func:`salvage_text_tool_calls`; ``take`` returns whatever is still held.
    """

    def __init__(self) -> None:
        self._pending = ""
        self.holding = False

    def feed(self, text: str) -> str:
        if self.holding:
            self._pending += text
            return ""
        buf = self._pending + text
        hits = [i for i in (buf.find(m) for m in TEXT_TOOL_CALL_MARKERS) if i >= 0]
        if hits:
            self.holding = True
            self._pending = buf[min(hits) :]
            return buf[: min(hits)]
        keep = next(
            (
                k
                for k in range(min(len(buf), max(map(len, TEXT_TOOL_CALL_MARKERS)) - 1), 0, -1)
                if any(m.startswith(buf[-k:]) for m in TEXT_TOOL_CALL_MARKERS)
            ),
            0,
        )
        self._pending = buf[len(buf) - keep :]
        return buf[: len(buf) - keep]

    def take(self) -> str:
        text, self._pending = self._pending, ""
        return text
