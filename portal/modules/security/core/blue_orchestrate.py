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

import re
from dataclasses import dataclass, field
from typing import Any

from .agentic_blue_eval import (
    Episode,
    _call_model,
    _find_balanced_json_objects,
    _query_real_telemetry,
)
from .analyst_verdict import SectionOutput
from .blue import _BLUE_SYSTEM_PROMPT_DISCOVERY
from .unknown_defense import MatchGrade, compute_similarity

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


# ── Slice 3: Reasoning section (Hunter) — open-ended discovery ──────────────

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_HUNTER_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nWhen you respond, include exactly one JSON object (in addition to any prose "
    "reasoning) with these fields:\n"
    '{"request_more": "<what telemetry you still need, or empty if you have enough>", '
    '"technique_ids": ["T...."], "evidence": ["..."], "reasoning": "...", '
    '"match_grade": "EXACT|SIMILAR|NONE", "similar_to": ["T...."]}\n'
    "Set request_more (non-empty) and leave technique_ids empty if you need more evidence "
    "before proposing anything — do not guess. You are proposing hypotheses for a domain "
    "expert to review; you are not issuing the final verdict."
)


def _strip_think_tags(text: str) -> str:
    """Strip inline <think>...</think> scratchpad blocks before parsing (I3).

    Ollama's reasoning API usually separates thinking from content already,
    but some fine-tunes (per the project's June zero-retry lesson) emit the
    scratchpad inline in `content` regardless — defensive strip either way.
    """
    return _THINK_TAG_RE.sub("", text or "").strip()


def format_for_reasoning(results: list[ToolResult], trigger: str) -> str:
    """Render gathered telemetry + trigger into the Hunter's context.

    Framed with blue._BLUE_SYSTEM_PROMPT_DISCOVERY (reused, open, no
    checklist) plus the structured-output instructions the Hunter needs to
    hand hypotheses to the expert (design §3.1.a / I8: never a checklist of
    *what to look for*, only of *how to answer*).
    """
    parts = [f"Trigger: {trigger}"]
    for r in results:
        parts.append(f"[{r.provenance}] query: {r.query}\n{r.raw_summary}")
    evidence_block = (
        "\n\n".join(parts) if results else f"Trigger: {trigger}\n(no telemetry gathered yet)"
    )
    return (
        f"{_BLUE_SYSTEM_PROMPT_DISCOVERY}\n\n{evidence_block}{_HUNTER_OUTPUT_FORMAT_INSTRUCTIONS}"
    )


def run_similarity(
    features: dict[str, Any], *, wiki_descriptions: dict[str, str]
) -> dict[str, Any]:
    """Run unknown_defense.compute_similarity and translate its grade into the
    analyst_verdict match_grade/similar_to carry (I8: a SIMILAR match is a
    named-variant lead, never coerced into EXACT or dropped)."""
    result = compute_similarity(features, wiki_descriptions)
    if result.grade == MatchGrade.NONE:
        return {"match_grade": "NONE", "similar_to": [], "similarity_detail": result.detail}
    return {
        "match_grade": result.grade,
        "similar_to": [result.matched_technique] if result.matched_technique else [],
        "similarity_detail": result.detail,
    }


def _parse_hunter_json(stripped: str) -> dict[str, Any] | None:
    for obj in reversed(_find_balanced_json_objects(stripped)):
        if "request_more" in obj or "technique_ids" in obj or "evidence" in obj:
            return obj
    return None


def run_reasoning_model(
    context: str,
    *,
    reasoning_model: str,
    ground_truth: set[str],
    dry_run: bool = False,
) -> SectionOutput:
    """Call a generalist reasoner (tools off) to hunt: form hypotheses, decide
    what more to pull, and carry a similarity result. The Hunter proposes; it
    never issues the section's terminal CONFIRMED (the expert does, Slice 4)."""
    if dry_run:
        return SectionOutput(
            request_more="dry-run: no live hunt performed",
            section="reasoning",
            raw="",
        )

    messages = [
        {"role": "system", "content": _BLUE_SYSTEM_PROMPT_DISCOVERY},
        {"role": "user", "content": context},
    ]
    msg = _call_model(reasoning_model, messages, tools=None, max_tokens=3000)
    content = msg.get("content", "") or ""
    stripped = _strip_think_tags(content)
    parsed = _parse_hunter_json(stripped)

    if not parsed:
        # No structured output at all -> treat as an insufficient-evidence
        # turn (I8: never guess a verdict from unparseable free text).
        fallback = stripped[:400] or "insufficient evidence — need more telemetry"
        return SectionOutput(request_more=fallback, section="reasoning", raw=content)

    request_more = str(parsed.get("request_more") or "").strip()
    technique_ids = [t for t in (parsed.get("technique_ids") or []) if t]
    match_grade = str(parsed.get("match_grade") or "NONE").upper()
    if match_grade not in ("EXACT", "SIMILAR", "NONE"):
        match_grade = "NONE"
    similar_to = [t for t in (parsed.get("similar_to") or []) if t]

    if request_more and not technique_ids:
        return SectionOutput(
            request_more=request_more,
            match_grade=match_grade,
            similar_to=similar_to,
            section="reasoning",
            raw=content,
        )

    if not technique_ids and not request_more:
        # Neither a hypothesis nor a request -> still insufficient (I8).
        return SectionOutput(
            request_more=stripped[:400] or "insufficient evidence — need more telemetry",
            section="reasoning",
            raw=content,
        )

    # A hypothesis set for the expert. Provisional only — section="reasoning"
    # marks it non-terminal; the orchestrator does not score this verdict.
    proposed_verdict = "ANOMALOUS_UNCLASSIFIED" if match_grade == "SIMILAR" else "CONFIRMED"
    return SectionOutput(
        verdict=proposed_verdict,
        technique_ids=technique_ids,
        evidence=[str(e) for e in (parsed.get("evidence") or [])],
        reasoning=str(parsed.get("reasoning") or ""),
        match_grade=match_grade,
        similar_to=similar_to,
        section="reasoning",
        raw=content,
    )
