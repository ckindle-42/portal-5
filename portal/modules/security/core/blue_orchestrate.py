"""Blue/Purple discovery orchestration: tool + reasoning + expert sections in a loop.

BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2. Purpose-built sections, right model in
the right space, looping until a conclusive expert verdict.

Reuses (never re-implements):
  - agentic_blue_eval: _call_model, normalize_tool_calls, _find_balanced_json_objects,
    _query_real_telemetry, _summarize_telemetry, score_findings_tiered, Episode, load_episode
  - blue: _fetch_blue_telemetry, _cite_or_drop, _BLUE_SYSTEM_PROMPT_DISCOVERY (the open hunt prompt)
  - unknown_defense: compute_similarity, MatchGrade  (the "find similar / novel" substrate)
  - platform.agent.run_loop  (deterministic orchestrator, Slice 5)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agentic_blue_eval import Episode, _call_model, _query_real_telemetry

# Retrieval-only tool schemas for the tool section (Retriever). report_detection
# is deliberately excluded here — the tool section gathers, it does not
# interpret or conclude (design §3.3; "DO NOT interpret" below).
_RETRIEVAL_TOOL_NAMES = (
    "query_splunk",
    "query_windows_events",
    "query_web_logs",
    "query_network_traffic",
)

_TOOL_SECTION_SYSTEM_PROMPT = (
    "You are a telemetry retrieval assistant supporting a security investigation. "
    "You have tools to pull Windows Security event logs, Splunk, web server logs, and "
    "network flow data. Given a request describing what to look for, call the most "
    "relevant tool(s) to gather telemetry. Prefer broad queries when the request is "
    "vague or you are unsure what will match — an empty narrow query wastes a turn. "
    "Do not interpret or conclude anything; just gather evidence."
)


def _retrieval_tool_schemas() -> list[dict]:
    from .agentic_blue_eval import _SEARCH_TOOLS

    return [t for t in _SEARCH_TOOLS if t.get("function", {}).get("name") in _RETRIEVAL_TOOL_NAMES]


@dataclass
class ToolResult:
    query: str
    rows: list[dict] = field(default_factory=list)
    provenance: str = (
        "matched-exact"  # matched-exact | live-broad-fallback | synthetic-fallback | empty
    )
    window: str = ""
    raw_summary: str = ""


@dataclass
class ToolRequest:
    spec: str
    window: str = ""
    prefer_broad: bool = True  # design §3.3 default toward universal queries


@dataclass
class SectionSpec:
    """One purpose-built section bound to a model. The orchestrator runs an
    ordered list of these (canonical: tool -> reasoning -> expert)."""

    role: str  # "tool" | "reasoning" | "expert"
    model: str
    needs_tools: bool = False  # True only for role == "tool"


def build_tool_request(trigger_or_more: str, *, window: str = "") -> ToolRequest:
    """Normalize an initial trigger OR a section's request_more into a ToolRequest.
    Retrieval only — no new offensive/synthesis capability. prefer_broad default."""
    return ToolRequest(spec=trigger_or_more.strip(), window=window)


def _dispatch_tool_call(name: str, args: dict, episode: Episode) -> str:
    """Answer one tool call against the episode's captured telemetry.

    Thin wrapper over agentic_blue_eval._query_real_telemetry (reused, not
    reimplemented) — this is what makes the tool leg hermetically testable
    with a fake Episode instead of a live Splunk/WinRM backend.
    """
    return _query_real_telemetry(name, episode, args)


def run_tool_model(
    req: ToolRequest,
    *,
    tool_model: str,
    ground_truth: set[str],
    episode: Episode,
    dry_run: bool = False,
) -> ToolResult:
    """Dispatch the tool model to gather telemetry for `req`.

    Composes reused primitives: _call_model (with retrieval-only tool schemas)
    -> tool_calls -> _query_real_telemetry per call -> broad fallback on empty
    (prefer_broad) -> ToolResult with provenance. DO NOT interpret.
    """
    tools = _retrieval_tool_schemas()
    messages = [
        {"role": "system", "content": _TOOL_SECTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"Investigation request: {req.spec}"},
    ]
    if dry_run:
        # No live model call — used by hermetic tests / --dry-run CLI paths.
        rows, empty = [], True
    else:
        msg = _call_model(tool_model, messages, tools=tools)
        tool_calls = msg.get("tool_calls") or []
        rows = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if name not in _RETRIEVAL_TOOL_NAMES:
                continue
            result_text = _dispatch_tool_call(name, args, episode)
            rows.append({"tool": name, "args": args, "result": result_text})
        empty = not rows or all(not r.get("result", "").strip() for r in rows)

    provenance = "matched-exact"
    if empty:
        if req.prefer_broad:
            # Broaden: a summary-style broad query against the whole episode,
            # bypassing keyword filtering (mirrors _query_real_telemetry's own
            # "no keywords -> summary" broadening, already landed f10fbee).
            has_any_telemetry = any(episode.telemetry.values())
            broad_text = _query_real_telemetry("query_splunk", episode, {})
            if has_any_telemetry and broad_text.strip():
                rows = [{"tool": "query_splunk", "args": {}, "result": broad_text}]
                provenance = "live-broad-fallback"
            else:
                provenance = "empty"
        else:
            provenance = "empty"

    raw_summary = "\n".join(r.get("result", "") for r in rows)[:4000]
    return ToolResult(
        query=req.spec, rows=rows, provenance=provenance, window=req.window, raw_summary=raw_summary
    )
