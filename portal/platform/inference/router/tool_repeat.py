"""Per-turn guard against a model re-issuing a tool call it already made.

Some models (Qwen3.8 on the compliance seat, measured 2026-10-16) answer a full tool result
by asking for the same call again, hop after hop, until the 20-hop limit ends the turn with no
answer. A repeat gains nothing: the result is already in the conversation. The guard returns the
earlier result with a short note instead of running the tool again, and on a third identical
request tells the loop to take a final turn with the tools withheld.

One guard lives for one turn. Nothing is kept across turns.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from portal.platform.inference.router.trace import note
from portal.platform.mcp_host.tool_support import (
    tool_result_byte_budget as _tool_result_byte_budget,
)

logger = logging.getLogger(__name__)


def tool_result_byte_budget(context_limit_tokens: int) -> int:
    """Keep the router's public budget helper backed by the shared derivation."""
    return _tool_result_byte_budget(context_limit_tokens)


REPEAT_NOTE = (
    "You already called this with the same arguments; the result is above. "
    "Use it to answer, or call a different tool."
)
#: Appended when the tools are withheld: the model is told to answer from what it has, because
#: a model that cannot call a tool otherwise writes the call out as text.
FINAL_ANSWER_REQUEST = {
    "role": "user",
    "content": (
        "No more tool calls are available. Using the tool results already above, give your "
        "final answer now."
    ),
}
#: Call-budget exhaustion asks for one cited answer with tools withheld.
CITED_SYNTHESIS_REQUEST = {
    "role": "user",
    "content": (
        "No more tool calls are available. Synthesize the tool results already above into "
        "one cited final answer now. Name the sources you used. Do not call a tool and do "
        "not return an empty reply."
    ),
}
#: Sent once on a workspace that requires a tool before it answers (portal.yaml
#: `require_tool_before_answer`) when a turn ended with an answer and no tool call.
GROUNDING_REQUEST = {
    "role": "user",
    "content": (
        "Answer only from a query result: call run_sql, profile_table, or execute_python "
        "first, then answer."
    ),
}
_QUERY_TOOLS = frozenset({"run_sql", "profile_table"})
#: Sent once when the request said tool_choice="required" and the first completion
#: answered with no tool call — Ollama cannot express "required" on /api/chat
#: (ollama_native._tools_for_choice), so the pipeline enforces it instead.
REQUIRED_TOOL_REQUEST = {
    "role": "user",
    "content": "This request requires a tool call: call one of the offered tools now, then answer from its result.",
}
UNGROUNDED_NOTICE = (
    "\n\n*Note: this answer is not grounded in a query — the model answered without running one.*"
)
#: The request count at which the turn stops offering tools (1 = executed, 2 = first repeat).
FORCE_SYNTHESIS_AT = 3


#: Tools whose result depends only on their arguments and on stored data nothing in the turn
#: edits: a repeat of one of these is a loop. Anything else (execute_*, create_*, remember,
#: write_*, an unknown tool) may change state, or read state a previous call changed, so it always
#: runs and invalidates what was cached: "edit, run the tests, edit, run the tests" repeats the same
#: `pytest` call with different results.
_READ_ONLY_PREFIXES = (
    "read_",
    "get_",
    "list_",
    "lookup_",
    "search_",
    "find_",
    "kb_search",
    "kb_list",
    "recall",
    "graph_recall",
    "neighbors",
    "entity_timeline",
    "nerc_cip_",
    "profile_table",
    "run_sql",
    "web_search",
    "web_fetch",
    "wiki_",
    "mitre_",
    "check_",
    "triage_",
    "scan_",
    "compliance_",
)
#: Compliance tools that write (the `compliance_` prefix is otherwise the reading surface).
_WRITING = frozenset(
    {
        "compliance_note",
        "compliance_correct",
        "compliance_review_decide",
        "compliance_review_decide_batch",
        "compliance_draft_revisions",
    }
)


def is_read_only(name: str) -> bool:
    return name.startswith(_READ_ONLY_PREFIXES) and name not in _WRITING


def _execute_python_succeeded(result: dict[str, Any]) -> bool:
    """True when the sandbox reported success. A mount or exit failure is not a computation."""
    try:
        payload = json.loads(result.get("content") or "")
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("success") is True


def _canonical_args(call: dict[str, Any]) -> str:
    raw: Any = (call.get("function") or {}).get("arguments")
    if isinstance(raw, str):
        text = raw.strip()
        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return text
    return json.dumps(raw if raw is not None else {}, sort_keys=True, separators=(",", ":"))


def call_key(call: dict[str, Any]) -> tuple[str, str]:
    """(tool name, canonical arguments): key order and whitespace never make a call new."""
    return (str((call.get("function") or {}).get("name", "")).strip(), _canonical_args(call))


class ToolRepeatGuard:
    """Remembers the calls a turn has executed and their results."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], str] = {}
        self._requests: dict[tuple[str, str], int] = {}
        self.force_synthesis = False
        self.suppressed = 0
        self.grounding_retried = False
        self.required_retried = False
        self.dispatched = False
        self._query_grounded = False

    def would_repeat(self, call: dict[str, Any]) -> bool:
        """True when this call would be served from the cache. Does not count it."""
        key = call_key(call)
        return is_read_only(key[0]) and key in self._results

    def seen(self, call: dict[str, Any]) -> bool:
        """True when this exact call already ran this turn; counts the request."""
        key = call_key(call)
        if not is_read_only(key[0]):
            # It will run, and what it does can change what an earlier identical call would now
            # return: nothing cached before it is a repeat any more.
            self._results.clear()
            self._requests.clear()
            return False
        self._requests[key] = self._requests.get(key, 0) + 1
        if key not in self._results:
            return False
        self.suppressed += 1
        if self._requests[key] >= FORCE_SYNTHESIS_AT:
            self.force_synthesis = True
        return True

    @property
    def executed(self) -> int:
        """Distinct tool calls this turn has run."""
        return len(self._results)

    def remember(self, call: dict[str, Any], result: dict[str, Any]) -> None:
        self.dispatched = (
            True  # a write counts: the required-tool retry must not drop the synthesis
        )
        key = call_key(call)
        name = key[0]
        if name in _QUERY_TOOLS or (name == "execute_python" and _execute_python_succeeded(result)):
            self._query_grounded = True  # a later write clears the read cache, not this
        if is_read_only(name):
            self._results[key] = str(result.get("content") or "")

    @property
    def grounded(self) -> bool:
        """True once a query, a successful execute_python, or any other read-only call has run."""
        return self._query_grounded or self.executed > 0

    def repeat_result(self, call: dict[str, Any]) -> dict[str, Any]:
        """The tool message for a suppressed repeat: the earlier result plus the note."""
        name = (call.get("function") or {}).get("name", "")
        earlier = self._results[call_key(call)]
        return {
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "name": name,
            "content": f"{earlier}\n\n[{REPEAT_NOTE}]",
        }


def prepare_toolless_finalizer(body: dict[str, Any], guard: ToolRepeatGuard) -> None:
    body["tools"] = None
    body["tool_choice"] = None
    messages = body.get("messages") or []
    if not messages or messages[-1] != FINAL_ANSWER_REQUEST:
        body["messages"] = [*messages, FINAL_ANSWER_REQUEST]
    guard.force_synthesis = True


def prepare_cited_synthesis(body: dict[str, Any], guard: ToolRepeatGuard) -> None:
    """Withhold tools and ask for one cited answer. ``tool_choice`` is ``none``."""
    body["tools"] = None
    body["tool_choice"] = "none"
    messages = body.get("messages") or []
    if not messages or messages[-1] != CITED_SYNTHESIS_REQUEST:
        body["messages"] = [*messages, CITED_SYNTHESIS_REQUEST]
    guard.force_synthesis = True


def clip_fresh_calls(
    calls: list[dict[str, Any]],
    repeat_flags: list[bool],
    dispatched: int,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Fresh-call prefix that fits ``limit``. Repeats are free. None keeps every call."""
    if limit is None:
        return list(calls), dispatched, False
    kept: list[dict[str, Any]] = []
    used = dispatched
    omitted = False
    for call, repeated in zip(calls, repeat_flags, strict=True):
        if not repeated and used >= limit:
            omitted = True
            break
        if not repeated:
            used += 1
        kept.append(call)
    return kept, used, omitted or used >= limit


@dataclass(frozen=True)
class ToolHopAction:
    """stop, synthesize, client, or dispatch for one hop's calls."""

    kind: str
    calls: list[dict[str, Any]]
    dispatched: int
    cited: bool = False


def _call_name(call: dict[str, Any]) -> str:
    return str((call.get("function") or {}).get("name", "")).strip()


def next_tool_action(
    *,
    hop: int,
    hop_limit: int,
    bite_returns_client: bool,
    synthesis_hop: bool,
    calls: list[dict[str, Any]],
    repeat_flags: list[bool],
    dispatched: int,
    call_limit: int | None,
    client_owned: bool,
    owned_names: set[str],
    client_tools_only: bool = False,
) -> ToolHopAction:
    """Choose dispatch, a client handoff, or one toolless synthesis for this hop."""
    if synthesis_hop:
        return ToolHopAction("stop", [], dispatched)
    if bite_returns_client:
        return ToolHopAction("client", list(calls), dispatched)
    if hop >= hop_limit:
        return ToolHopAction("synthesize", [], dispatched, cited=call_limit is not None)
    if call_limit is not None and client_owned and not client_tools_only:
        # The cap seals OWUI's outer loop; client-only callers run their own loop and are exempt.
        owned = [
            (call, flag)
            for call, flag in zip(calls, repeat_flags, strict=True)
            if _call_name(call) in owned_names
        ]
        kept, used, _spent = clip_fresh_calls(
            [call for call, _flag in owned],
            [flag for _call, flag in owned],
            dispatched,
            call_limit,
        )
        if not kept:
            return ToolHopAction("synthesize", [], dispatched, cited=True)
        return ToolHopAction("dispatch", kept, used, cited=True)
    kept, used, spent = clip_fresh_calls(calls, repeat_flags, dispatched, call_limit)
    if not kept:
        return ToolHopAction("synthesize", [], dispatched, cited=True)
    if client_owned:
        return ToolHopAction("client", list(calls), dispatched)
    if spent:
        return ToolHopAction("dispatch", kept, used, cited=True)
    return ToolHopAction("dispatch", kept, used, cited=False)


def followup_tool_choice(choice: Any, calls: list[dict[str, Any]]) -> Any:
    """The choice after a tool result: "required" is spent by any call, a named tool only by its own."""
    if choice == "required":
        return "auto"
    named = (choice.get("function") or {}).get("name") if isinstance(choice, dict) else None
    if named and any((c.get("function") or {}).get("name") == named for c in calls):
        return "auto"
    return choice


def hold_ungrounded_answer(
    guard: ToolRepeatGuard, require_tool: bool, required_choice: bool, tools_offered: bool
) -> bool:
    """True when this hop's answer should be held for one tool-call retry."""
    if not tools_offered or guard.grounding_retried or guard.required_retried:
        return False
    if require_tool and not guard.grounded:
        return True
    return required_choice and not guard.dispatched


def no_tool_call_retry(guard: ToolRepeatGuard, require_tool: bool) -> dict[str, str] | None:
    """The one follow-up message for an answer given with no tool call, or ``None``
    when this turn's single retry is spent. A ``require_tool_before_answer`` workspace
    gets the grounding ask; any other request gets the call-first ask, which is how
    ``tool_choice="required"`` is enforced (Ollama cannot express it)."""
    if require_tool:
        if guard.grounding_retried:
            return None
        guard.grounding_retried = True
        return GROUNDING_REQUEST
    if guard.required_retried:
        return None
    guard.required_retried = True
    note(required_tool_retried=True)
    return REQUIRED_TOOL_REQUEST


def _content_bytes(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, bytes):
        return len(content)
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    return len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _truncate_tool_content(content: Any, max_bytes: int) -> str:
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    elif isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    marker = "\n[Tool result truncated: byte budget reached; remaining output omitted.]"
    marker_bytes = marker.encode("utf-8")
    if max_bytes < len(marker_bytes):
        marker = next(
            (
                item
                for item in ("[cut:budget]", "[cut:limit]", "[cut:b]", "[cut]", "!")
                if len(item.encode("utf-8")) <= max_bytes
            ),
            "",
        )
        marker_bytes = marker.encode("utf-8")
        if not marker_bytes:
            return ""
    head_bytes = text.encode("utf-8")[: max_bytes - len(marker_bytes)]
    return head_bytes.decode("utf-8", errors="ignore") + marker


def _effective_tool_budget(content: Any, budget: int) -> int:
    """Allow self-budgeted dual_document payloads their declared window bytes, capped at 3x."""
    if budget <= 0 or not isinstance(content, str) or "dual_document" not in content[:256]:
        return budget
    try:
        parsed = json.loads(content)
    except ValueError:
        return budget
    if not isinstance(parsed, dict) or parsed.get("mode") != "dual_document":
        return budget
    window = parsed.get("window")
    if not isinstance(window, dict) or window.get("fits") is not True:
        return budget
    budget_tokens = window.get("budget_tokens")
    bytes_per_token = window.get("bytes_per_token")
    if not isinstance(budget_tokens, int) or not isinstance(bytes_per_token, (int, float)):
        return budget
    declared = int(budget_tokens * float(bytes_per_token)) + 32_768
    return max(budget, min(declared, budget * 3))


def apply_tool_byte_budget(
    accumulated: int,
    results: list[dict[str, Any]],
    budget: int,
    workspace_id: str,
) -> int:
    """Add role:tool bytes and truncate new results to the remaining context budget."""
    total = accumulated
    for msg in results:
        if msg.get("role") == "tool":
            size = _content_bytes(msg.get("content"))
            eff_budget = _effective_tool_budget(msg.get("content"), budget)
            remaining = max(0, eff_budget - total) if eff_budget > 0 else size
            if eff_budget > 0 and size > remaining:
                msg["content"] = _truncate_tool_content(msg.get("content"), remaining)
                logger.info(
                    "Tool-loop result truncated: workspace=%s accumulated=%d budget=%d",
                    workspace_id,
                    total + size,
                    eff_budget,
                )
                size = _content_bytes(msg.get("content"))
            total += size
    return total
