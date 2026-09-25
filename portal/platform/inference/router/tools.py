"""MCP tool dispatch for the chat-completion tool loop.

Houses ``_dispatch_tool_call`` and its private helpers. Calls the shared
``tool_registry`` singleton and workspace tool helpers. Depends on
metrics, state, and tool_registry; never imports router_pipe.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from portal.platform.inference.router.metrics import (
    _tool_call_duration,
    _tool_call_errors,
    _tool_calls_total,
)
from portal.platform.inference.router.state import _record_error
from portal.platform.inference.router.trace import (
    capture as trace_capture,
)
from portal.platform.inference.router.trace import (
    span as trace_span,
)

logger = logging.getLogger(__name__)


_CREATE_ACTION_RE = re.compile(r"\b(?:build|create|generate|make|produce|save)\b")
_RUN_ACTION_RE = re.compile(r"\b(?:execute|run)\b")
# TASK_COMPLIANCE_REASONING_V2 P8-L tried forcing tool_choice=required onto
# nerc_cip_requirement for any message naming a CIP id plus a word like
# "requirement" or "means" — the same mechanism used for
# create_word_document/execute_python below, applied to a lookup instead of
# a side effect. TASK_COMPLIANCE_PROVE_THE_MODULE_V1 §P4.1: that word list
# ("requirement", "requirements", "say", "says", "state", "states", "mean",
# "means", "text", "verbatim") is compliance-reading's own core vocabulary —
# an analyst asking "what does CIP-007-6 R2 require?" matched it, got forced
# onto a single tool, named a different one anyway (per its system prompt),
# had that call dropped by the whitelist gate, and the turn ended unanswered
# with the dispatch counter unmoved. Killed turns in three separate
# measurements (closeout/p8, splash_sweep/p4, contract_and_close/p5); every
# time the recorded workaround was to reword the question. A question is not
# a side effect — the candidate is removed, not just re-tuned.


def _unwrap_tool_name_envelope(arguments: dict[str, Any]) -> dict[str, Any]:
    """Some models (command-r confirmed via WFE 2026-09-11) emit tool-call
    arguments wrapped as {"tool_name": ..., "parameters": {...}} instead of
    the OpenAI tool-call contract's flat kwargs — the function name is
    already known from ``tool_call["function"]["name"]``, so every such call
    dispatched with the wrapper keys instead of real parameters and failed
    every turn. Unwrap it so the call still dispatches.
    """
    params = arguments.get("parameters")
    if set(arguments) <= {"tool_name", "parameters"} and isinstance(params, dict):
        return params
    return arguments


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


def _last_user_content(messages: list[dict[str, Any]]) -> str:
    """Return the last user turn as plain text, including multimodal text parts."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return str(content)
    return ""


def _select_explicit_required_tool(
    messages: list[dict[str, Any]], effective_tools: set[str]
) -> str | None:
    """Select one allow-listed tool when the user explicitly requires its side effect.

    A single-tool schema plus ``tool_choice=required`` avoids the model failure
    where a multi-tool payload produces a narrated pseudo-call in content instead
    of a native ``tool_calls`` result. Matching is deliberately conservative:
    general coding or document-writing prompts retain the full tool set and
    ``tool_choice=auto``.
    """
    text = _last_user_content(messages).lower()
    if not text:
        return None

    candidates: list[tuple[str, bool]] = [
        (
            "create_powerpoint",
            bool(_CREATE_ACTION_RE.search(text))
            and any(term in text for term in ("powerpoint", "power point", ".pptx", "slide deck")),
        ),
        (
            "create_excel",
            bool(_CREATE_ACTION_RE.search(text))
            and any(term in text for term in ("excel", ".xlsx", "spreadsheet", "workbook")),
        ),
        (
            "create_word_document",
            bool(_CREATE_ACTION_RE.search(text))
            and any(term in text for term in ("word document", ".docx")),
        ),
        (
            "execute_bash",
            bool(_RUN_ACTION_RE.search(text))
            and any(term in text for term in ("bash", "shell command", "```sh", "```shell")),
        ),
        (
            "execute_nodejs",
            bool(_RUN_ACTION_RE.search(text))
            and any(term in text for term in ("node.js", "nodejs", "javascript", "```js")),
        ),
        (
            "execute_python",
            bool(_RUN_ACTION_RE.search(text))
            and (
                "python" in text
                or "```py" in text
                or re.search(r"(?m)^\s*(?:from\s+\S+\s+import|import\s+\S+)", text) is not None
            ),
        ),
    ]
    for tool_name, matched in candidates:
        if matched and tool_name in effective_tools:
            return tool_name
    return None


async def _dispatch_tool_call(
    tool_call: dict[str, Any],
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
) -> dict[str, Any]:
    """Whitelist-check and dispatch one model-emitted tool call.

    The single chokepoint between the model's ``tool_calls`` array and
    the registry dispatcher. Every tool the model asks for comes
    through here. **Never raises** — every failure path returns a
    ``tool``-role message with an ``{"error": "..."}`` payload that
    the caller appends to ``messages[]`` and the model interprets.
    This is what lets the streaming tool loop in chunk 3 keep its
    SSE stream alive across tool failures.

    Three failure paths, all metric-tagged and returning an error
    message:

    1. **JSON parse fails** on ``tool_call.function.arguments`` →
       error type ``tool_arg_parse``.
    2. **Tool not whitelisted** for this workspace × persona →
       error type ``tool_not_allowed``. This is the least-privilege
       gate. ``effective_tools`` is resolved by
       ``_resolve_persona_tools`` at the call site; a tool absent
       from that set cannot be called even if the registry has it
       healthy. The split between this whitelist and the registry's
       circuit breaker is deliberate: this is "is this combination
       authorized?", the registry is "is this tool reachable?".
    3. **Registry dispatch returns ``{"error": ...}``** → emitted
       as the tool's content; metrics tag ``tool_call_errors``.

    Records three Prometheus metrics on every dispatch (success or
    error): ``portal5_tool_calls_total``,
    ``portal5_tool_call_duration_seconds``, and
    ``portal5_tool_call_errors_total`` (on error only).

    Lazy-imports the ``tool_registry`` singleton on first call to
    keep test stubbing simple (patch the module attribute before
    any request flows through here).

    Args:
        tool_call: One element of the model's ``tool_calls`` array,
            shaped ``{"id": str, "function": {"name": str,
            "arguments": str (JSON)}}``.
        effective_tools: Authorized tool names for this workspace ×
            persona combination. From ``_resolve_persona_tools``.
        workspace_id: For metric labels and error logging.
        persona: For error-message text and logging.
        request_id: Forwarded to ``tool_registry.dispatch`` for
            cross-log correlation between pipeline and MCP servers.

    Returns:
        A ``tool``-role message dict shaped
        ``{"role": "tool", "tool_call_id": str, "name": str,
        "content": str}`` where ``content`` is JSON-encoded.
    """
    from portal.platform.inference.tool_registry import tool_registry

    fn = tool_call.get("function", {})
    tool_name = fn.get("name", "").strip()
    arguments_str = fn.get("arguments", "{}")
    tool_call_id = tool_call.get("id", "")
    allowed = tool_name in effective_tools
    trace_span(
        "tool.requested",
        tool=tool_name,
        tool_call_id=tool_call_id,
        allowed=allowed,
    )

    # Parse arguments
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        _record_error(workspace_id, "tool_arg_parse")
        trace_span(
            "tool.completed",
            tool=tool_name,
            tool_call_id=tool_call_id,
            outcome="invalid_arguments",
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Invalid JSON arguments: {arguments_str[:200]}"}),
        }
    arguments = _unwrap_tool_name_envelope(arguments)
    trace_capture(tool_arguments={tool_name: arguments})

    # Whitelist enforcement
    if not allowed:
        _record_error(workspace_id, "tool_not_allowed")
        trace_span(
            "tool.completed",
            tool=tool_name,
            tool_call_id=tool_call_id,
            outcome="not_allowed",
        )
        logger.warning(
            "Tool %s called but not in workspace=%s persona=%s whitelist; rejected",
            tool_name,
            workspace_id,
            persona,
        )
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Tool '{tool_name}' not available for {persona}"}),
        }

    # Dispatch via registry
    t0 = time.monotonic()
    try:
        result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)
    except Exception:
        trace_span(
            "tool.completed",
            tool=tool_name,
            tool_call_id=tool_call_id,
            outcome="exception",
            duration_ms=round((time.monotonic() - t0) * 1000, 1),
        )
        raise
    elapsed = time.monotonic() - t0
    trace_span(
        "tool.completed",
        tool=tool_name,
        tool_call_id=tool_call_id,
        outcome="error" if "error" in result else "ok",
        duration_ms=round(elapsed * 1000, 1),
    )

    # Metrics
    _tool_calls_total.labels(tool=tool_name, workspace=workspace_id).inc()
    _tool_call_duration.labels(tool=tool_name).observe(elapsed)
    if "error" in result:
        _tool_call_errors.labels(tool=tool_name, workspace=workspace_id).inc()

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
    }
