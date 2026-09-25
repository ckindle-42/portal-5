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


def salvage_text_tool_calls(
    content: str, tools: list[dict[str, Any]] | None
) -> tuple[str, list[dict[str, Any]]]:
    """Recover Qwen3-Coder XML tool calls written into ``content``.

    Only calls naming an offered tool count; anything else returns no calls so
    the text is delivered unchanged. Returns ``(text_before_the_call, calls)``
    with calls in OpenAI ``tool_calls`` shape (arguments as a JSON string).
    """
    offered = {
        (t.get("function") or {}).get("name"): (t.get("function") or {}).get("parameters") or {}
        for t in tools or []
    }
    matches = list(_XML_FUNCTION_RE.finditer(content or ""))
    if not matches or any(m.group(1) not in offered for m in matches):
        return content, []
    calls: list[dict[str, Any]] = []
    for i, m in enumerate(matches):
        props = offered[m.group(1)].get("properties") or {}
        args = {
            name: _xml_param_value(raw, props.get(name) or {})
            for name, raw in _XML_PARAMETER_RE.findall(m.group(2))
        }
        calls.append(
            {
                "id": f"call_text_{i}",
                "type": "function",
                "function": {"name": m.group(1), "arguments": json.dumps(args)},
            }
        )
    prefix = content[: matches[0].start()].replace("<tool_call>", "").strip()
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
