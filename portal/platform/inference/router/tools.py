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

from portal.platform.inference.router.metrics import (
    _tool_call_duration,
    _tool_call_errors,
    _tool_calls_total,
)
from portal.platform.inference.router.state import _record_error

logger = logging.getLogger(__name__)


_CREATE_ACTION_RE = re.compile(r"\b(?:build|create|generate|make|produce|save)\b")
_RUN_ACTION_RE = re.compile(r"\b(?:execute|run)\b")
# TASK_COMPLIANCE_REASONING_V2 P8-L live finding: with the full compliance
# tool set offered under tool_choice=auto, the deployed model repeatedly
# chose browser_navigate/web_search over nerc_cip_requirement for an exact
# "what does CIP-XXX-Y RZ require" question even after its description and
# the persona's system_prompt_append were both corrected to prefer it —
# fixing the instructions did not change the model's own tool-choice
# judgment. Forcing tool_choice=required with a single-tool schema (the same
# mechanism already used for create_word_document/execute_python below) does
# not depend on that judgment.
_CIP_ID_RE = re.compile(r"\bcip-\d{3}(?:-\d+(?:\.\d+\w*)?)?\b")
_REQUIREMENT_LOOKUP_RE = re.compile(
    r"\b(require|requires|requirement|requirements|say|says|state|states|mean|means|text|verbatim)\b"
)


def _last_user_content(messages: list[dict]) -> str:
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


def _select_explicit_required_tool(messages: list[dict], effective_tools: set[str]) -> str | None:
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
            "nerc_cip_requirement",
            bool(_CIP_ID_RE.search(text)) and bool(_REQUIREMENT_LOOKUP_RE.search(text)),
        ),
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
    tool_call: dict,
    effective_tools: set[str],
    workspace_id: str,
    persona: str,
    request_id: str,
) -> dict:
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

    # Parse arguments
    try:
        arguments = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        _record_error(workspace_id, "tool_arg_parse")
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": json.dumps({"error": f"Invalid JSON arguments: {arguments_str[:200]}"}),
        }

    # Whitelist enforcement
    if tool_name not in effective_tools:
        _record_error(workspace_id, "tool_not_allowed")
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
    result = await tool_registry.dispatch(tool_name, arguments, request_id=request_id)
    elapsed = time.monotonic() - t0

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
