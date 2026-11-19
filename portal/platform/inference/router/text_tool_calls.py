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
# P5-GEMMA4-TOOLTEXT-001: Gemma 4's native call form — the canonical chat
# template shipped in the served checkpoints renders assistant tool_calls as
# ``<|tool_call>call:name{key:<|"|>value<|"|>}<tool_call|>`` (Ollama's
# PARSER gemma4 parses the same tokens) — reaches clients as plain content
# whenever an engine's parser is bypassed (a hop with no tools offered, or a
# parse miss). One rendered live (2026-11-19) went to an OWUI user verbatim.
GEMMA_TOOL_CALL_OPEN = "<|tool_call>"
GEMMA_TOOL_CALL_CLOSE = "<tool_call|>"
_GEMMA_STRING_QUOTE = '<|"|>'

# P5-IFM-TOOLTEXT-001: IFM-lineage checkpoints (K2-Horizon-MoVA, the
# auto-reasoning seat) write calls as an ``<ifm|tool_calls>`` block whose
# ``<ifm|tool_call>`` entries carry ``<ifm|arg_key>``/``<ifm|arg_value>`` pairs
# (the served checkpoint's chat template also defines a json and a typed form).
# It reaches plain content whenever an engine parser is bypassed or a parse
# misses — the toolless Jarvis planner turn emitted it verbatim on 2026-11-19.
IFM_TOOL_CALLS_OPEN = "<ifm|tool_calls>"
IFM_TOOL_CALL_OPEN = "<ifm|tool_call>"
IFM_TOOL_CALL_CLOSE = "</ifm|tool_call>"
IFM_ARG_KEY_OPEN = "<ifm|arg_key>"
IFM_ARG_KEY_CLOSE = "</ifm|arg_key>"
IFM_ARG_TYPE_OPEN = "<ifm|arg_type>"
IFM_ARG_TYPE_CLOSE = "</ifm|arg_type>"
IFM_ARG_VALUE_OPEN = "<ifm|arg_value>"
IFM_ARG_VALUE_CLOSE = "</ifm|arg_value>"
_IFM_CALL_RE = re.compile(
    re.escape(IFM_TOOL_CALL_OPEN)
    + r"(?:\s*(\{.*?\})\s*|([^{}\n<]+?)[ \t]*\n(.*?))"
    + re.escape(IFM_TOOL_CALL_CLOSE),
    re.DOTALL,
)
_IFM_ARG_RE = re.compile(
    re.escape(IFM_ARG_KEY_OPEN)
    + r"(.*?)"
    + re.escape(IFM_ARG_KEY_CLOSE)
    + r"\s*(?:"
    + re.escape(IFM_ARG_TYPE_OPEN)
    + r"(.*?)"
    + re.escape(IFM_ARG_TYPE_CLOSE)
    + r"\s*)?"
    + re.escape(IFM_ARG_VALUE_OPEN)
    + r"(.*?)"
    + re.escape(IFM_ARG_VALUE_CLOSE),
    re.DOTALL,
)
TEXT_TOOL_CALL_MARKERS = (
    "<tool_call>",
    "<function=",
    GEMMA_TOOL_CALL_OPEN,
    IFM_TOOL_CALL_OPEN,
    IFM_TOOL_CALLS_OPEN,
)
_TOOL_CALL_WRAPPER_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
_XML_FUNCTION_RE = re.compile(r"<function=([^>\s]+)>(.*?)</function>", re.DOTALL)
_XML_PARAMETER_RE = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)
_GEMMA_CALL_RE = re.compile(r"<\|tool_call>call:([^\s{}]+?)\s*\{")
_GEMMA_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


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
    except json.JSONDecodeError as exc:
        # Live granite/oMLX (2026-10-15) closed a call like Python source:
        # ``{"code": "print(1)")}}`` — a stray ``)`` after a complete string value.
        # Drop that single character and decode once more; any other defect stays
        # unparsed.
        if raw_payload[exc.pos : exc.pos + 1] != ")":
            return None
        try:
            payload, end = json.JSONDecoder().raw_decode(
                raw_payload[: exc.pos] + raw_payload[exc.pos + 1 :]
            )
        except json.JSONDecodeError:
            return None
        raw_payload = raw_payload[: exc.pos] + raw_payload[exc.pos + 1 :]
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


def _gemma_ws(raw: str, i: int) -> int:
    while i < len(raw) and raw[i] in " \t\r\n":
        i += 1
    return i


def _gemma_string(raw: str, i: int) -> tuple[str, int] | None:
    """The ``<|"|>``-quoted string starting at *i*: its body and the index past
    the closing quote. The format escapes nothing (the template writes argument
    values verbatim), so the body may itself contain braces, colons, quotes."""
    start = i + len(_GEMMA_STRING_QUOTE)
    end = raw.find(_GEMMA_STRING_QUOTE, start)
    return None if end < 0 else (raw[start:end], end + len(_GEMMA_STRING_QUOTE))


def _gemma_object(raw: str, i: int) -> tuple[dict[str, Any], int] | None:
    out: dict[str, Any] = {}
    i = _gemma_ws(raw, i + 1)  # step over '{'
    while True:
        if raw.startswith("}", i):
            return out, i + 1
        if raw.startswith(_GEMMA_STRING_QUOTE, i):
            got = _gemma_string(raw, i)
            if got is None:
                return None
            key, i = got
        else:
            colon = raw.find(":", i)
            if colon < 0:
                return None
            key, i = raw[i:colon].strip(), colon
        pair = _gemma_value(raw, i + 1)  # step over ':'
        if pair is None:
            return None
        out[key] = pair[0]
        i = _gemma_ws(raw, pair[1])
        if raw.startswith(",", i):
            i = _gemma_ws(raw, i + 1)
        elif not raw.startswith("}", i):
            return None


def _gemma_array(raw: str, i: int) -> tuple[list[Any], int] | None:
    out: list[Any] = []
    i = _gemma_ws(raw, i + 1)  # step over '['
    while True:
        if raw.startswith("]", i):
            return out, i + 1
        pair = _gemma_value(raw, i)
        if pair is None:
            return None
        out.append(pair[0])
        i = _gemma_ws(raw, pair[1])
        if raw.startswith(",", i):
            i = _gemma_ws(raw, i + 1)
        elif not raw.startswith("]", i):
            return None


def _gemma_value(raw: str, i: int) -> tuple[Any, int] | None:
    """One Gemma-4 argument value at *i* with the index past it: a quoted
    string, nested object/array, ``true``/``false``/``null``, or a number."""
    i = _gemma_ws(raw, i)
    if raw.startswith(_GEMMA_STRING_QUOTE, i):
        got = _gemma_string(raw, i)
        return None if got is None else (got[0], got[1])
    for literal, value in (("true", True), ("false", False), ("null", None)):
        if raw.startswith(literal, i):
            return value, i + len(literal)
    if raw.startswith("{", i):
        return _gemma_object(raw, i)
    if raw.startswith("[", i):
        return _gemma_array(raw, i)
    number = _GEMMA_NUMBER_RE.match(raw, i)
    if number:
        return json.loads(number.group(0)), number.end()
    return None


def _decode_gemma_call(text: str, match: re.Match[str]) -> tuple[str, dict[str, Any]] | None:
    """(name, arguments) for one ``<|tool_call>call:…{…}<tool_call|>`` block.

    The block must close on the format's own token with nothing but whitespace
    between the arguments and it; anything else stays unparsed."""
    value = _gemma_value(text, match.end() - 1)  # re-parse the '{' the match ended on
    if value is None or not isinstance(value[0], dict):
        return None
    close = text.find(GEMMA_TOOL_CALL_CLOSE, value[1])
    if close < 0 or text[value[1] : close].strip():
        return None
    name = match.group(1).strip()
    if name.startswith(_GEMMA_STRING_QUOTE) and name.endswith(_GEMMA_STRING_QUOTE):
        name = name[len(_GEMMA_STRING_QUOTE) : -len(_GEMMA_STRING_QUOTE)]
    return name, value[0]


def _decode_ifm_arguments(raw: str) -> dict[str, str] | None:
    """``<ifm|arg_key>``/``<ifm|arg_value>`` pairs tiling *raw* (a type tag
    may sit between them), as ``key -> raw value``; None on anything left over."""
    arguments: dict[str, str] = {}
    pos = 0
    for m in _IFM_ARG_RE.finditer(raw):
        if raw[pos : m.start()].strip():
            return None
        arguments[m.group(1)] = m.group(3)
        pos = m.end()
    if raw[pos:].strip():
        return None
    return arguments


def _decode_ifm_call(
    match: re.Match[str], offered: dict[Any, dict[str, Any]]
) -> tuple[str, dict[str, Any]] | None:
    """(name, arguments) for one ``<ifm|tool_call>`` block: the template's
    json form (one object per call) or its xml form (name line plus pairs)."""
    if match.group(1) is not None:
        return _decode_json_call(match.group(1))
    name = match.group(2).strip()
    raw_args = _decode_ifm_arguments(match.group(3))
    if raw_args is None:
        return None
    props = offered.get(name, {}).get("properties") or {}
    return name, {
        key: _xml_param_value(value, props.get(key) or {}) for key, value in raw_args.items()
    }


def salvage_text_tool_calls(
    content: str, tools: list[dict[str, Any]] | None
) -> tuple[str, list[dict[str, Any]]]:
    """Recover JSON, XML, Gemma-4, or IFM tool calls written into ``content``.

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

    for match in _GEMMA_CALL_RE.finditer(text):
        decoded = _decode_gemma_call(text, match)
        if decoded is None:
            return content, []
        matches.append((match.start(), *decoded))

    for match in _IFM_CALL_RE.finditer(text):
        decoded = _decode_ifm_call(match, offered)
        if decoded is None:
            return content, []
        matches.append((match.start(), *decoded))

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
    first = matches[0][0]
    wrapper = text.find(IFM_TOOL_CALLS_OPEN, 0, first)
    prefix = text[: wrapper if wrapper >= 0 else first].replace("<tool_call>", "").strip()
    return prefix, calls


def drop_unparsed_markup(text: str) -> str:
    """*text* cut at its first unsalvageable call opener (``<tool_call>``,
    ``<|tool_call>``, ``<ifm|tool_call(s)>``): call syntax is never an answer,
    so it is not delivered to a client.
    A bare ``<function=...>`` mention stays (it may be prose about an unoffered tool)."""
    cuts = [
        c
        for c in (
            text.find("<tool_call>"),
            text.find(GEMMA_TOOL_CALL_OPEN),
            text.find(IFM_TOOL_CALL_OPEN),
            text.find(IFM_TOOL_CALLS_OPEN),
        )
        if c >= 0
    ]

    return text[: min(cuts)].rstrip() if cuts else text


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
