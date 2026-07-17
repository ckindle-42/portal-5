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
from .blue import _BLUE_SYSTEM_PROMPT_DISCOVERY, _cite_or_drop
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


def _coerce_tool_args(raw: Any) -> dict:
    """Ollama's native tool-call arguments are usually already a dict, but a
    live probe against granite4.1:8b-ctx8k (Slice 7 end-to-end run) found it
    can return `arguments` as a JSON-encoded string instead — crashing
    _query_real_telemetry's `.values()` call downstream. Defensive parse."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


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
            args = _coerce_tool_args(fn.get("arguments"))
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


# ── Slice 4: Expert section (fed, no tools) — the conclusive verdict ────────

_EXPERT_SYSTEM_PROMPT = (
    "You are a domain-expert security analyst rendering a conclusive judgment. You have no "
    "tools and cannot fetch more data — you must decide based on what is given to you. A "
    "hunter analyst has proposed hypotheses and gathered evidence; your job is to confirm, "
    "refute, or reclassify them as a security expert would, grounding every conclusion "
    "strictly in the evidence provided. Never invent supporting evidence that isn't there."
)

_EXPERT_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nRespond with exactly one JSON object:\n"
    '{"verdict": "CONFIRMED|ANOMALOUS_UNCLASSIFIED|RULED_OUT", "technique_ids": ["T...."], '
    '"evidence": ["..."], "reasoning": "...", "match_grade": "EXACT|SIMILAR|NONE", '
    '"similar_to": ["T...."], "request_more": "<leave empty unless you need one specific '
    'targeted gap filled before you can conclude>"}\n'
    "Set request_more only if a single specific gap would let you conclude — otherwise render "
    "your best-grounded verdict now; RULED_OUT is a valid, honest conclusion when the evidence "
    "does not support the hunter's hypothesis."
)


def format_for_expert(reasoning_out: SectionOutput, results: list[ToolResult], trigger: str) -> str:
    """A focused 'here is what the hunt found; render your expert judgment'
    prompt — distinct from the open hunt prompt (the expert is fed, not
    exploring)."""
    evidence_lines = [f"[{r.provenance}] {r.query}: {r.raw_summary}" for r in results]
    hunter_block = (
        f"Hunter's proposed verdict: {reasoning_out.verdict or '(none — requested more evidence)'}\n"
        f"Hunter's proposed technique_ids: {reasoning_out.technique_ids}\n"
        f"Hunter's evidence: {reasoning_out.evidence}\n"
        f"Hunter's reasoning: {reasoning_out.reasoning}\n"
        f"Hunter's similarity result: match_grade={reasoning_out.match_grade}, "
        f"similar_to={reasoning_out.similar_to}"
    )
    return (
        f"Trigger: {trigger}\n\n{hunter_block}\n\nGathered telemetry:\n" + "\n".join(evidence_lines)
        if evidence_lines
        else f"Trigger: {trigger}\n\n{hunter_block}\n\n(no telemetry gathered)"
    )


def _combined_telemetry_text(results: list[ToolResult]) -> dict[str, dict]:
    combined = "\n".join(r.raw_summary for r in results)
    return {"gathered": {"telemetry": combined, "source": "tool-section"}}


def run_expert_model(
    context: str,
    *,
    expert_model: str,
    ground_truth: set[str],
    tool_results: list[ToolResult] | None = None,
    hunter_similar_to: list[str] | None = None,
    dry_run: bool = False,
) -> SectionOutput:
    """Call the fed, no-tools domain-expert model for the conclusive verdict.

    Deliberately never passes `tools` and never checks any backends.yaml
    `supports_tools` gate — this is the require_tools=False path that makes a
    supports_tools:false expert (Foundation-Sec-8B-Reasoning) usable. A
    CONFIRMED verdict is run through blue._cite_or_drop; if its evidence
    doesn't survive, it is downgraded to ANOMALOUS_UNCLASSIFIED (I2/I8),
    carrying the Hunter's similar_to when the expert didn't supply its own.
    """
    if dry_run:
        return SectionOutput(
            request_more="dry-run: no live expert call performed", section="expert"
        )

    messages = [
        {"role": "system", "content": _EXPERT_SYSTEM_PROMPT},
        {"role": "user", "content": context + _EXPERT_OUTPUT_FORMAT_INSTRUCTIONS},
    ]
    msg = _call_model(expert_model, messages, tools=None, max_tokens=3000)
    content = msg.get("content", "") or ""
    stripped = _strip_think_tags(content)
    parsed = None
    for obj in reversed(_find_balanced_json_objects(stripped)):
        if "verdict" in obj or "request_more" in obj:
            parsed = obj
            break

    if not parsed:
        fallback = (
            stripped[:400] or "expert produced no parseable verdict — need one targeted re-check"
        )
        return SectionOutput(request_more=fallback, section="expert", raw=content)

    verdict = parsed.get("verdict")
    if verdict not in ("CONFIRMED", "ANOMALOUS_UNCLASSIFIED", "RULED_OUT"):
        verdict = None
    request_more = str(parsed.get("request_more") or "").strip()
    technique_ids = [t for t in (parsed.get("technique_ids") or []) if t]
    evidence = [str(e) for e in (parsed.get("evidence") or [])]
    reasoning = str(parsed.get("reasoning") or "")
    match_grade = str(parsed.get("match_grade") or "NONE").upper()
    if match_grade not in ("EXACT", "SIMILAR", "NONE"):
        match_grade = "NONE"
    similar_to = [t for t in (parsed.get("similar_to") or []) if t] or list(hunter_similar_to or [])

    if verdict is None and not request_more:
        request_more = stripped[:400] or "expert produced no verdict — need one targeted re-check"

    if verdict is None:
        return SectionOutput(
            request_more=request_more,
            match_grade=match_grade,
            similar_to=similar_to,
            section="expert",
            raw=content,
        )

    if verdict == "CONFIRMED":
        telemetry = _combined_telemetry_text(tool_results or [])
        reported = [{"technique_id": t, "evidence": "; ".join(evidence)} for t in technique_ids]
        kept = _cite_or_drop(reported, telemetry, list(ground_truth))
        kept_ids = {d.get("technique_id", "").upper() for d in kept}
        if not technique_ids or kept_ids != {t.upper() for t in technique_ids}:
            # Evidence didn't fully survive citation -- never-invent (I2):
            # downgrade rather than let an uncited CONFIRMED stand.
            return SectionOutput(
                verdict="ANOMALOUS_UNCLASSIFIED",
                technique_ids=technique_ids,
                evidence=evidence,
                reasoning=reasoning
                or "downgraded: CONFIRMED evidence did not survive cite-or-drop",
                match_grade=match_grade if match_grade != "NONE" else "SIMILAR",
                similar_to=similar_to or technique_ids,
                section="expert",
                raw=content,
            )

    return SectionOutput(
        verdict=verdict,
        technique_ids=technique_ids,
        evidence=evidence,
        reasoning=reasoning,
        match_grade=match_grade,
        similar_to=similar_to,
        section="expert",
        raw=content,
    )


# ── Slice 5: Deterministic section-pipeline orchestrator (GATE-B) ──────────
#
# GATE-B spike outcome: FORCED to a bespoke state machine, not run_loop.
# platform/agent/loop.py::run_loop + decide.py::decide_next_action are built
# around CapabilityProvider.query()+rank() — open-ended selection over an
# *indexed capability graph*, where the loop doesn't know in advance which
# capability runs next. This pipeline is the opposite shape: a fixed,
# strictly-ordered 3-stage flow (tool -> reasoning -> expert) with typed data
# threading between stages (ToolResult accumulation feeding format_for_reasoning,
# the Hunter's SectionOutput feeding format_for_expert). Forcing that into
# run_loop would mean building a synthetic 3-candidate capability graph whose
# "ranking" is just the fixed order we already have — pure indirection, no
# reduction in code and no use of run_loop's actual value (open capability
# selection). A small bespoke loop here is the honest, auditable shape;
# run_loop remains available for a future *open-ended* section (e.g. a variable
# number of specialist consultants), which this build's canonical 3-section
# pipeline is not.


@dataclass
class OrchestrationResult:
    """Final result of one run_blue_orchestration call.

    `verdict` is one of ANALYST_VERDICTS; UNRESOLVED means the orchestrator
    (not any section) gave up on budget — distinct from a section-produced
    ANOMALOUS_UNCLASSIFIED (§3.2; I8: a real discovery is never punished by
    looking like a stall). `capability_verdict` is intentionally left for the
    caller to fill in from the untouched episode.derive_verdict harness axis
    (I1) — this module never computes it.
    """

    verdict: str = "UNRESOLVED"
    technique_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    match_grade: str = "NONE"
    similar_to: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    rounds: int = 0
    elapsed_s: float = 0.0
    capability_verdict: str | None = None


def run_blue_orchestration(
    episode: Episode,
    *,
    sections: list[SectionSpec],
    max_rounds: int = 6,
    wall_clock_s: float | None = None,
    check_additional: bool = False,
    dry_run: bool = False,
) -> OrchestrationResult:
    """Run the canonical tool -> reasoning -> expert pipeline to a conclusive
    expert verdict, or UNRESOLVED on budget exhaustion.

    `sections` binds each role to a model (canonical: [tool, reasoning,
    expert]) — swapping a section's model, or adding a 4th role later, is a
    config change to this list, not a rewrite of the flow below (§0.1(2)).
    """
    import time as _time

    models = {s.role: s.model for s in sections}
    for role in ("tool", "reasoning", "expert"):
        if role not in models:
            raise ValueError(f"sections is missing a '{role}' SectionSpec")

    ground_truth = set(episode.techniques)
    trigger = f"An alert was triggered on {episode.target_host} (scenario: {episode.scenario})."

    tool_results: list[ToolResult] = []
    trace: list[dict] = []
    rounds = 0
    started = _time.monotonic()
    hunter_out: SectionOutput | None = None
    expert_out: SectionOutput | None = None

    def _elapsed() -> float:
        return _time.monotonic() - started

    def _budget_exhausted() -> bool:
        if rounds >= max_rounds:
            return True
        return bool(wall_clock_s and _elapsed() >= wall_clock_s)

    def _gather(request_more: str) -> None:
        req = build_tool_request(request_more)
        tr = run_tool_model(
            req,
            tool_model=models["tool"],
            ground_truth=ground_truth,
            episode=episode,
            dry_run=dry_run,
        )
        tool_results.append(tr)
        trace.append(
            {
                "round": rounds,
                "section": "tool",
                "model": models["tool"],
                "provenance": tr.provenance,
                "query": tr.query,
            }
        )

    while not _budget_exhausted():
        ctx = format_for_reasoning(tool_results, trigger)
        hunter_out = run_reasoning_model(
            ctx, reasoning_model=models["reasoning"], ground_truth=ground_truth, dry_run=dry_run
        )
        trace.append(
            {
                "round": rounds,
                "section": "reasoning",
                "model": models["reasoning"],
                "verdict": hunter_out.verdict,
                "match_grade": hunter_out.match_grade,
                "wants_more": hunter_out.wants_more(),
            }
        )
        rounds += 1

        if hunter_out.wants_more():
            if _budget_exhausted():
                break
            _gather(hunter_out.request_more)
            rounds += 1
            continue

        ectx = format_for_expert(hunter_out, tool_results, trigger)
        expert_out = run_expert_model(
            ectx,
            expert_model=models["expert"],
            ground_truth=ground_truth,
            tool_results=tool_results,
            hunter_similar_to=hunter_out.similar_to,
            dry_run=dry_run,
        )
        trace.append(
            {
                "round": rounds,
                "section": "expert",
                "model": models["expert"],
                "verdict": expert_out.verdict,
                "match_grade": expert_out.match_grade,
                "wants_more": expert_out.wants_more(),
            }
        )
        rounds += 1

        if expert_out.is_conclusion():
            break
        if expert_out.wants_more() and not _budget_exhausted():
            _gather(expert_out.request_more)
            rounds += 1
            continue
        break

    if expert_out is not None and expert_out.is_conclusion():
        result = OrchestrationResult(
            verdict=expert_out.verdict,
            technique_ids=expert_out.technique_ids,
            evidence=expert_out.evidence,
            reasoning=expert_out.reasoning,
            match_grade=expert_out.match_grade,
            similar_to=expert_out.similar_to,
            trace=trace,
            rounds=rounds,
            elapsed_s=round(_elapsed(), 2),
        )
    else:
        result = OrchestrationResult(
            verdict="UNRESOLVED",
            trace=trace,
            rounds=rounds,
            elapsed_s=round(_elapsed(), 2),
        )

    if check_additional and result.verdict != "UNRESOLVED":
        # design §3.1.b: one more pass to surface other findings after a
        # conclusion. Left as a documented no-op for this slice — the trace
        # already records every round for a human to review manually; a real
        # second pass is a follow-on once Slice 8's ablation shows it's worth
        # the extra round cost.
        pass

    return result
