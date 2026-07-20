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

# Live-verified finding (Slice 7/8 pre-screen, 2026-07-17): 3000 tokens is
# tight enough that a heavy chain-of-thought reasoning model (observed on
# deepseek-r1:32b) can run out mid-thought right as it reaches its
# conclusion — response cut off mid-sentence, no closing JSON ever emitted.
# The Hunter/expert then correctly (I8) treat the truncated garble as
# insufficient evidence and request more, which looks identical to genuine
# non-convergence but is actually a token-budget artifact. Raised generously
# for both sections; a "thinking" model's visible <think> block competes
# with its own JSON answer for this same budget.
_REASONING_MAX_TOKENS = 8000
_EXPERT_MAX_TOKENS = 8000

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


def _stringify_query_args(args: dict) -> dict:
    """Flatten list/int-valued args to strings before _query_real_telemetry.

    Live-verified root cause (Slice 8 pre-screen, 2026-07-17): every Hunter
    candidate tried (devstral, deepseek-r1, granite4.1:30b) kept re-asking for
    telemetry it had already been "given" — because _query_real_telemetry's
    keyword extraction only scans string-valued query_args, and
    query_windows_events's OWN tool schema types `event_ids` as an array of
    integers. A perfectly well-formed structured call like
    query_windows_events(event_ids=[4769, 4776]) therefore never narrowed the
    query at all — it silently fell through to the generic broad-summary
    branch every round, so no Hunter model was ever actually receiving the
    narrower evidence it asked for, regardless of how well it reasoned.
    _query_real_telemetry itself is I7-protected (additive-only); this
    normalizes the args shape at the call site instead.
    """
    out: dict = {}
    for k, v in args.items():
        if isinstance(v, list):
            out[k] = " ".join(str(x) for x in v)
        elif isinstance(v, (int, float)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


_BROAD_SUMMARY_RE = re.compile(r"^\d+ events: ")

# Real MITRE ATT&CK technique IDs are Txxxx or Txxxx.xxx — nothing looser.
# This is NOT a claim that every real technique is enumerable or that an
# unmapped finding is invalid (I8: novelty is a legitimate outcome, and
# ANOMALOUS_UNCLASSIFIED/RULED_OUT are never required to name a specific
# known ID at all — an empty or absent technique_id there is fine). CONFIRMED
# is the one verdict that claims "I've matched this to a specific known
# technique" — that's an inherently specific claim, so if what's offered
# doesn't even parse as a real ID (found live 2026-07-18: a "T...." literal
# slipped through as CONFIRMED), the claim doesn't hold up, same class of
# problem as evidence that doesn't survive citation.
_TECHNIQUE_ID_RE = re.compile(r"^T\d{4}(\.\d{3})?$")


def _all_technique_ids_well_formed(technique_ids: list[str]) -> bool:
    return bool(technique_ids) and all(_TECHNIQUE_ID_RE.match(t.upper()) for t in technique_ids)


# Words too generic to narrow anything (query framing filler, not evidence
# terms) — kept short and conservative; anything not on this list is a
# candidate keyword.
_FREETEXT_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "for",
        "to",
        "and",
        "or",
        "in",
        "on",
        "at",
        "with",
        "from",
        "log",
        "logs",
        "details",
        "detail",
        "full",
        "data",
        "all",
        "any",
        "related",
        "access",
        "additional",
        "specific",
        "information",
        "context",
        "including",
        "showing",
        "during",
        "around",
        "over",
        "into",
        "that",
        "this",
        "these",
        "those",
        "host",
        "hosts",
    }
)


def _freetext_narrow(args: dict, episode: Episode) -> str | None:
    """Fallback narrowing for tool-call args with no literal EventCode/
    technique-ID pattern (query_web_logs/query_network_traffic/query_splunk
    calls framed as free text, e.g. filter="Tomcat manager interface").

    _query_real_telemetry's own keyword extraction is Windows-EventCode/
    MITRE-ID-centric only (I7 forbids extending it) — live-verified on
    meta3_tomcat_manager (2026-07-17): a request for "Tomcat manager
    interface access" never narrowed at all, always returning the generic
    cross-sourcetype event summary instead of the actual matching web/ftp
    log lines, even though those lines exist in the episode. This is a
    substring fallback confined to blue_orchestrate.py — additive-only,
    does not touch agentic_blue_eval.py.
    """
    words: set[str] = set()
    for v in args.values():
        if not isinstance(v, str):
            continue
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_/.-]{2,}", v.lower()):
            if w not in _FREETEXT_STOPWORDS:
                words.add(w)
    if not words:
        return None

    matches: list[str] = []
    for source_type, lines in episode.telemetry.items():
        for line in lines:
            low = line.lower()
            if any(w in low for w in words):
                matches.append(f"[{source_type}] {line}")
    if not matches:
        return None
    return "\n".join(matches[:50])[:2500]


def _dispatch_tool_call(name: str, args: dict, episode: Episode) -> str:
    """Answer one tool call against the episode's captured telemetry.

    Thin wrapper over agentic_blue_eval._query_real_telemetry (reused, not
    reimplemented) — this is what makes the tool leg hermetically testable
    with a fake Episode instead of a live Splunk/WinRM backend. Falls back
    to _freetext_narrow when the reused primitive's EventCode/technique-ID-
    only extraction couldn't narrow the query (still returned the generic
    broad summary) but the args contain free-text terms that DO match
    something in the episode's raw telemetry.
    """
    result = _query_real_telemetry(name, episode, _stringify_query_args(args))
    if _BROAD_SUMMARY_RE.match(result):
        narrowed = _freetext_narrow(args, episode)
        if narrowed:
            return narrowed
    return result


_WINDOWS_EVENT_HINT_RE = re.compile(
    r"\bEvent\s*ID\b|\bEventCode\b|\bWindows\s+Security\b|\b4\d{3}\b", re.IGNORECASE
)


def _bias_tool_schemas(req_spec: str, tools: list[dict]) -> list[dict]:
    """Narrow the offered tool schemas to query_windows_events when the
    request unambiguously names a Windows Security EventCode/Event ID.

    Live-verified root cause (Slice 8 ablation, 2026-07-18): the Hunter asked
    for "Event ID 4769" by name, but the small tool model called
    query_network_traffic instead — a plausible-sounding but wrong pick from
    4 similarly-described retrieval tools — getting back a useless generic
    event-count summary. The Hunter then still claimed EXACT match and
    fabricated specific details (account names, encryption types) that were
    never actually in that summary — a confabulation the Expert later
    (correctly) rejected, but only after burning a full round. When the
    request is this unambiguous, don't leave the choice to the small model.
    """
    if not _WINDOWS_EVENT_HINT_RE.search(req_spec):
        return tools
    narrowed = [t for t in tools if t.get("function", {}).get("name") == "query_windows_events"]
    return narrowed or tools


def run_tool_model(
    req: ToolRequest,
    *,
    tool_model: str,
    ground_truth: set[str],
    episode: Episode,
    dry_run: bool = False,
) -> ToolResult:
    """Dispatch the tool model to gather telemetry for `req`.

    Composes reused primitives: _call_model (with retrieval-only tool schemas,
    biased toward query_windows_events when the request unambiguously names a
    Windows EventCode — see _bias_tool_schemas) -> tool_calls ->
    _query_real_telemetry per call -> broad fallback on empty (prefer_broad)
    -> ToolResult with provenance. DO NOT interpret.
    """
    tools = _bias_tool_schemas(req.spec, _retrieval_tool_schemas())
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
    "expert to review; you are not issuing the final verdict. Every entry in `evidence` must "
    "be something you can point to verbatim in the telemetry you were actually given — never "
    "cite a detail (an account name, an encryption type, a tool name) just because it's typical "
    "of the technique you suspect; if the telemetry doesn't show it, that detail doesn't belong "
    "in `evidence`. If request_more is non-empty, name the exact gap (which EventCode/field/"
    "technique you still need to see) — never a generic re-ask for 'more logs'."
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


def format_new_evidence(results: list[ToolResult]) -> str:
    """Render ONLY newly-gathered telemetry as a follow-up turn.

    Found live 2026-07-18 (BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2 Slice 8
    model comparison): run_reasoning_model rebuilt a fresh system+user
    message pair from scratch every hunt-loop round, re-rendering the ENTIRE
    accumulated tool_results pile each time via format_for_reasoning — the
    Hunter had zero memory of its own prior reasoning turns, so every round
    was a cold re-derivation from a growing evidence dump rather than genuine
    iterative refinement. Combined with real multi-turn history (see
    run_reasoning_model's `history` param), this renders only the NEW
    evidence gathered since the Hunter's last turn — the model already has
    everything earlier in its own conversation history, so re-sending it
    would both bloat context (quadratic growth across rounds) and dilute the
    model's own prior reasoning with a wall of repeated telemetry.
    """
    if not results:
        return f"(no new telemetry gathered){_HUNTER_OUTPUT_FORMAT_INSTRUCTIONS}"
    parts = [f"[{r.provenance}] query: {r.query}\n{r.raw_summary}" for r in results]
    return (
        "New telemetry gathered in response to your request:\n\n"
        + "\n\n".join(parts)
        + _HUNTER_OUTPUT_FORMAT_INSTRUCTIONS
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
    history: list[dict] | None = None,
    dry_run: bool = False,
) -> SectionOutput:
    """Call a generalist reasoner (tools off) to hunt: form hypotheses, decide
    what more to pull, and carry a similarity result. The Hunter proposes; it
    never issues the section's terminal CONFIRMED (the expert does, Slice 4).

    `history` carries the Hunter's own prior turns in this hunt loop (user/
    assistant pairs) so it can build on its own reasoning across rounds
    instead of cold-restarting on a growing evidence pile each time (found
    live 2026-07-18 — see format_new_evidence's docstring for the full
    story). Optional and defaults to None for callers that want a single
    isolated turn (e.g. the Slice 3 unit tests, or a one-shot probe).
    """
    if dry_run:
        return SectionOutput(
            request_more="dry-run: no live hunt performed",
            section="reasoning",
            raw="",
        )

    messages = [{"role": "system", "content": _BLUE_SYSTEM_PROMPT_DISCOVERY}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": context})
    msg = _call_model(reasoning_model, messages, tools=None, max_tokens=_REASONING_MAX_TOKENS)
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
    "Set request_more only if a single specific gap would let you conclude — name the exact "
    "EventCode/field/technique that gap is about, never a generic re-ask — otherwise render "
    "your best-grounded verdict now; RULED_OUT is a valid, honest conclusion when the evidence "
    "does not support the hunter's hypothesis."
)


def format_for_expert(
    reasoning_out: SectionOutput,
    results: list[ToolResult],
    trigger: str,
    hunter_history: list[dict] | None = None,
) -> str:
    """A focused 'here is what the hunt found; render your expert judgment'
    prompt — distinct from the open hunt prompt (the expert is fed, not
    exploring).

    `hunter_history` (optional, additive): the Hunter's own accumulated
    multi-round conversation, if any. Previously the Expert only ever saw
    reasoning_out's terminal evidence/reasoning fields — a one-shot,
    already-compressed restatement of however many rounds the Hunter spent
    narrowing down a hypothesis, with the actual back-and-forth that
    produced it thrown away. Found live 2026-07-20 (GATE-D validation): this
    is a real information-loss point distinct from the 2-section "merged"
    arm, where the same model instance that reasoned across all rounds also
    renders the final verdict, so it never goes through this compression
    step at all. Safe to forward here despite the Hunter's own history cap
    existing specifically to prevent quadratic growth *within* the Hunter's
    own loop (re-sending the whole accumulated pile every round) — the
    round budget already caps how many Hunter turns can occur before
    hand-off (3 by default, `_hunter_stall_cap`), so this is a small,
    one-time cost at hand-off, not a recurring per-round one.
    """
    evidence_lines = [f"[{r.provenance}] {r.query}: {r.raw_summary}" for r in results]
    history_block = ""
    if hunter_history:
        turns = [f"  {m['role']}: {m['content']}" for m in hunter_history if m.get("content")]
        if turns:
            history_block = (
                "Hunter's investigation history (own reasoning across rounds):\n"
                + "\n".join(turns)
                + "\n\n"
            )
    hunter_block = (
        f"Hunter's proposed verdict: {reasoning_out.verdict or '(none — requested more evidence)'}\n"
        f"Hunter's proposed technique_ids: {reasoning_out.technique_ids}\n"
        f"Hunter's evidence: {reasoning_out.evidence}\n"
        f"Hunter's reasoning: {reasoning_out.reasoning}\n"
        f"Hunter's similarity result: match_grade={reasoning_out.match_grade}, "
        f"similar_to={reasoning_out.similar_to}"
    )
    return (
        f"Trigger: {trigger}\n\n{history_block}{hunter_block}\n\nGathered telemetry:\n"
        + "\n".join(evidence_lines)
        if evidence_lines
        else f"Trigger: {trigger}\n\n{history_block}{hunter_block}\n\n(no telemetry gathered)"
    )


def _combined_telemetry_text(results: list[ToolResult]) -> dict[str, dict]:
    combined = "\n".join(r.raw_summary for r in results)
    return {"gathered": {"telemetry": combined, "source": "tool-section"}}


_wiki_technique_descriptions_cache: dict[str, str] | None = None


def _wiki_technique_descriptions() -> dict[str, str]:
    """Process-lifetime cache — the wiki-seeded technique descriptions don't
    change mid-run, and this gets called at least once per Hunter round plus
    once per Expert/merged conclusion across the whole corpus."""
    global _wiki_technique_descriptions_cache
    if _wiki_technique_descriptions_cache is None:
        from .blue import _load_wiki_technique_descriptions

        _wiki_technique_descriptions_cache = _load_wiki_technique_descriptions()
    return _wiki_technique_descriptions_cache


def _ground_similarity(out: SectionOutput, tool_results: list[ToolResult]) -> SectionOutput:
    """Replace the model's self-reported match_grade/similar_to with the
    deterministic U1 similarity computation (unknown_defense.compute_similarity)
    against real gathered telemetry + the wiki's seeded technique descriptions.

    Root cause (found live 2026-07-19/20, GATE-D ablation): `run_similarity()`
    already existed in this module and is unit-tested in isolation
    (test_blue_orchestrate_reasoning.py), but was never actually called from
    the live Hunter/Expert/merged flow below — every match_grade/similar_to
    in a corpus run was pure unverified LLM self-report in a JSON field, with
    zero connection to the wiki-grounded engine built for exactly this. That
    made NOVELTY structurally ~0 regardless of model capability: the "known
    unknown, flag it as SIMILAR" case this whole design exists to catch
    (I8; Part II-A's Council rationale) was never actually measurable,
    because nothing ever computed a grounded SIMILAR. Same never-invent
    spirit as _cite_or_drop/_ground_hunter_evidence, extended from the
    exact-technique axis to the similarity axis: don't trust an unverified
    "this looks similar to X" claim any more than an unverified "this IS X."

    Skips (returns `out` unchanged) when there's no telemetry gathered yet or
    the wiki hasn't been seeded — honestly reports NONE rather than fabricate
    a grounded verdict from nothing (mirrors compute_similarity's own
    no-wiki-data contract).
    """
    if not tool_results:
        return out
    wiki_descriptions = _wiki_technique_descriptions()
    if not wiki_descriptions:
        return out

    observed_features = {
        "telemetry": "\n".join(r.raw_summary for r in tool_results),
        "reported_techniques": list(out.technique_ids),
        "sources": [r.provenance for r in tool_results],
    }
    similarity = compute_similarity(observed_features, wiki_descriptions)
    grounded_similar_to = [similarity.matched_technique] if similarity.matched_technique else []
    return SectionOutput(
        verdict=out.verdict,
        technique_ids=out.technique_ids,
        evidence=out.evidence,
        reasoning=out.reasoning,
        request_more=out.request_more,
        match_grade=similarity.grade,
        similar_to=grounded_similar_to,
        section=out.section,
        raw=out.raw,
    )


def _ground_hunter_evidence(
    hunter_out: SectionOutput, tool_results: list[ToolResult], ground_truth: set[str]
) -> SectionOutput:
    """Catch Hunter confabulation one round before it reaches the Expert.

    Live-verified (Slice 8 ablation, 2026-07-18): given a weak/mismatched
    tool result, the Hunter still claimed EXACT match and cited specific
    details (account names, encryption types, tool names) that were never
    actually present in the gathered telemetry — plausible textbook
    knowledge, not evidence it retrieved. The Expert (correctly, I2) refused
    to confirm it, but only after a full round was already spent. Reuses the
    same _cite_or_drop gate already applied to the Expert's CONFIRMED —
    additive, not a new grounding mechanism — so an ungrounded hypothesis is
    caught here and turned into a request_more that names the specific
    technique(s) that didn't survive citation, rather than being forwarded
    to the Expert as if it were solid.
    """
    if hunter_out.verdict is None or not hunter_out.technique_ids or not tool_results:
        # Nothing gathered yet to cite against — not the failure mode this
        # guards against (a mismatched/wrong tool result the Hunter then
        # embellished past), so don't punish a hypothesis formed before any
        # tool round has run.
        return hunter_out
    telemetry = _combined_telemetry_text(tool_results)
    reported = [
        {"technique_id": t, "evidence": "; ".join(hunter_out.evidence)}
        for t in hunter_out.technique_ids
    ]
    kept = _cite_or_drop(reported, telemetry, list(ground_truth))
    kept_ids = {d.get("technique_id", "").upper() for d in kept}
    if kept_ids == {t.upper() for t in hunter_out.technique_ids}:
        return hunter_out
    ungrounded = [t for t in hunter_out.technique_ids if t.upper() not in kept_ids]
    return SectionOutput(
        request_more=(
            f"Your cited evidence for {ungrounded} did not survive a citation check against "
            "the telemetry actually gathered so far — it wasn't literally present in what was "
            "retrieved. Re-query for that specific evidence (exact EventCode/field), or "
            "reconsider your hypothesis using only what has actually been returned."
        ),
        section="reasoning",
        raw=hunter_out.raw,
    )


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
    msg = _call_model(expert_model, messages, tools=None, max_tokens=_EXPERT_MAX_TOKENS)
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
        malformed = not _all_technique_ids_well_formed(technique_ids)
        if not technique_ids or kept_ids != {t.upper() for t in technique_ids} or malformed:
            # Evidence didn't fully survive citation, or the claimed ID(s)
            # don't even parse as real MITRE IDs -- never-invent (I2):
            # downgrade rather than let an uncited or malformed-ID CONFIRMED
            # stand. Only CONFIRMED is held to this — ANOMALOUS_UNCLASSIFIED
            # below is never required to name a specific known ID (I8).
            return SectionOutput(
                verdict="ANOMALOUS_UNCLASSIFIED",
                technique_ids=technique_ids,
                evidence=evidence,
                reasoning=reasoning
                or (
                    "downgraded: CONFIRMED technique_id(s) did not parse as real MITRE IDs"
                    if malformed
                    else "downgraded: CONFIRMED evidence did not survive cite-or-drop"
                ),
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


# ── Slice 8: Merged reasoning/expert role — the 2-section "V1 shape" ────────
#
# design §6.1 / build-doc Slice 8: the ablation's 2-section arm is "tool +
# merged reasoning/expert" — one generalist model both hunts (open discovery,
# decides what more to pull, runs similarity/novelty detection) AND renders
# the conclusive verdict itself, instead of a separate Hunter proposing to a
# separate fed expert. Additive-only (I7): the canonical 3-section pipeline
# above is untouched; this is a second, optional pipeline shape selected by
# which roles are present in `sections`.

_MERGED_SYSTEM_PROMPT = (
    _BLUE_SYSTEM_PROMPT_DISCOVERY
    + "\n\nUnlike a hunter proposing hypotheses to someone else, you are the "
    "sole analyst here: you both investigate and render the conclusive "
    "verdict yourself. Ground every conclusion strictly in evidence given to "
    "you or gathered on your request — never invent supporting evidence."
)

_MERGED_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nWhen you respond, include exactly one JSON object (in addition to any prose "
    "reasoning) with these fields:\n"
    '{"request_more": "<what telemetry you still need, or empty if you have enough to '
    'conclude>", "verdict": "CONFIRMED|ANOMALOUS_UNCLASSIFIED|RULED_OUT (omit/empty if '
    'requesting more)", "technique_ids": ["T...."], "evidence": ["..."], "reasoning": "...", '
    '"match_grade": "EXACT|SIMILAR|NONE", "similar_to": ["T...."]}\n'
    "Set request_more (non-empty) and leave verdict empty if you need more evidence before "
    "concluding — do not guess. Otherwise render your best-grounded verdict now; RULED_OUT is "
    "a valid, honest conclusion when the evidence does not support your hypothesis."
)


def format_for_merged(results: list[ToolResult], trigger: str) -> str:
    """Render gathered telemetry + trigger for the merged role's first turn —
    same open-discovery framing as format_for_reasoning, but paired with the
    merged output contract (a verdict field, not just a hypothesis)."""
    parts = [f"Trigger: {trigger}"]
    for r in results:
        parts.append(f"[{r.provenance}] query: {r.query}\n{r.raw_summary}")
    evidence_block = (
        "\n\n".join(parts) if results else f"Trigger: {trigger}\n(no telemetry gathered yet)"
    )
    return f"{evidence_block}{_MERGED_OUTPUT_FORMAT_INSTRUCTIONS}"


def format_new_evidence_merged(results: list[ToolResult]) -> str:
    """Merged-role analogue of format_new_evidence — delta-only follow-up
    turn, paired with the merged output contract."""
    if not results:
        return f"(no new telemetry gathered){_MERGED_OUTPUT_FORMAT_INSTRUCTIONS}"
    parts = [f"[{r.provenance}] query: {r.query}\n{r.raw_summary}" for r in results]
    return (
        "New telemetry gathered in response to your request:\n\n"
        + "\n\n".join(parts)
        + _MERGED_OUTPUT_FORMAT_INSTRUCTIONS
    )


def run_merged_model(
    context: str,
    *,
    merged_model: str,
    ground_truth: set[str],
    tool_results: list[ToolResult] | None = None,
    history: list[dict] | None = None,
    dry_run: bool = False,
) -> SectionOutput:
    """Call one generalist model to both hunt and render the conclusive
    verdict — the 2-section "V1 shape" ablation arm (design §6.1, build-doc
    Slice 8). Same never-invent citation gate as the expert (I2): a CONFIRMED
    verdict is run through blue._cite_or_drop, downgraded to
    ANOMALOUS_UNCLASSIFIED if its evidence doesn't survive."""
    if dry_run:
        return SectionOutput(
            request_more="dry-run: no live merged call performed", section="merged"
        )

    messages = [{"role": "system", "content": _MERGED_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": context})
    msg = _call_model(merged_model, messages, tools=None, max_tokens=_REASONING_MAX_TOKENS)
    content = msg.get("content", "") or ""
    stripped = _strip_think_tags(content)
    parsed = None
    for obj in reversed(_find_balanced_json_objects(stripped)):
        if "verdict" in obj or "request_more" in obj:
            parsed = obj
            break

    if not parsed:
        fallback = stripped[:400] or "insufficient evidence — need more telemetry"
        return SectionOutput(request_more=fallback, section="merged", raw=content)

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
    similar_to = [t for t in (parsed.get("similar_to") or []) if t]

    if verdict is None and not request_more:
        request_more = stripped[:400] or "insufficient evidence — need more telemetry"

    if verdict is None:
        return SectionOutput(
            request_more=request_more,
            match_grade=match_grade,
            similar_to=similar_to,
            section="merged",
            raw=content,
        )

    if verdict == "CONFIRMED":
        telemetry = _combined_telemetry_text(tool_results or [])
        reported = [{"technique_id": t, "evidence": "; ".join(evidence)} for t in technique_ids]
        kept = _cite_or_drop(reported, telemetry, list(ground_truth))
        kept_ids = {d.get("technique_id", "").upper() for d in kept}
        malformed = not _all_technique_ids_well_formed(technique_ids)
        if not technique_ids or kept_ids != {t.upper() for t in technique_ids} or malformed:
            return SectionOutput(
                verdict="ANOMALOUS_UNCLASSIFIED",
                technique_ids=technique_ids,
                evidence=evidence,
                reasoning=reasoning
                or (
                    "downgraded: CONFIRMED technique_id(s) did not parse as real MITRE IDs"
                    if malformed
                    else "downgraded: CONFIRMED evidence did not survive cite-or-drop"
                ),
                match_grade=match_grade if match_grade != "NONE" else "SIMILAR",
                similar_to=similar_to or technique_ids,
                section="merged",
                raw=content,
            )

    return SectionOutput(
        verdict=verdict,
        technique_ids=technique_ids,
        evidence=evidence,
        reasoning=reasoning,
        match_grade=match_grade,
        similar_to=similar_to,
        section="merged",
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
    """Run the section pipeline to a conclusive verdict, or UNRESOLVED on
    budget exhaustion.

    `sections` binds each role to a model. Two shapes are accepted: the
    canonical 3-section pipeline (`[tool, reasoning, expert]`) and the
    2-section ablation arm (`[tool, merged]`, design §6.1 / build-doc
    Slice 8's "V1 shape") where one generalist model both hunts and renders
    the verdict itself. Swapping a section's model is a config change to
    this list, not a rewrite of the flow below (§0.1(2)).
    """
    models = {s.role: s.model for s in sections}
    has_three = {"tool", "reasoning", "expert"} <= models.keys()
    has_two = {"tool", "merged"} <= models.keys()
    if not has_three and not has_two:
        raise ValueError(
            "sections must contain {'tool','reasoning','expert'} (3-section canonical) "
            "or {'tool','merged'} (2-section ablation arm)"
        )
    if has_two and not has_three:
        return _run_two_section(
            episode,
            models=models,
            max_rounds=max_rounds,
            wall_clock_s=wall_clock_s,
            dry_run=dry_run,
        )
    return _run_three_section(
        episode,
        models=models,
        max_rounds=max_rounds,
        wall_clock_s=wall_clock_s,
        check_additional=check_additional,
        dry_run=dry_run,
    )


def _run_three_section(
    episode: Episode,
    *,
    models: dict[str, str],
    max_rounds: int,
    wall_clock_s: float | None,
    check_additional: bool,
    dry_run: bool,
) -> OrchestrationResult:
    import time as _time

    ground_truth = set(episode.techniques)
    trigger = f"An alert was triggered on {episode.target_host} (scenario: {episode.scenario})."

    tool_results: list[ToolResult] = []
    trace: list[dict] = []
    rounds = 0
    started = _time.monotonic()
    hunter_out: SectionOutput | None = None
    expert_out: SectionOutput | None = None

    # Hunter conversation continuity (found live 2026-07-18 — see
    # format_new_evidence's docstring): the Hunter needs its own prior
    # reasoning turns to genuinely refine across rounds instead of
    # cold-restarting on a growing evidence pile each time. Bounded to keep
    # context growth linear rather than quadratic: each turn carries only
    # the NEW evidence gathered since the Hunter's last turn (not the whole
    # accumulated pile), and the history itself is capped to the most recent
    # _hunter_history_cap_pairs turn-pairs as a defensive backstop beyond
    # whatever max_rounds already bounds it to.
    hunter_history: list[dict] = []
    new_since_last_hunt: list[ToolResult] = []
    _hunter_history_cap_pairs = 6
    _hunter_history_turn_cap_chars = 3000

    # Stall handoff (live-verified 2026-07-18, meta3_tomcat_manager): the
    # Hunter's own output contract has no way to say "I've searched enough,
    # nothing here" — it can only propose a hypothesis or request_more, so a
    # genuinely exhausted search (the model's own reasoning text conceding
    # "no concrete indicators found," round after round) still forces
    # wants_more()=True and loops until max_rounds, never reaching the
    # Expert at all. After _hunter_stall_cap consecutive rounds with no
    # hypothesis proposed, hand off to the Expert anyway with a note that
    # the search appears exhausted — I8-safe: this never tells the Expert
    # what to conclude, only that it's the Expert's turn to render its own
    # honest judgment (RULED_OUT/ANOMALOUS_UNCLASSIFIED are valid) instead of
    # the loop silently running out the clock.
    _hunter_stall_cap = 3
    consecutive_no_hypothesis_rounds = 0

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
        new_since_last_hunt.append(tr)
        trace.append(
            {
                "round": rounds,
                "section": "tool",
                "model": models["tool"],
                "provenance": tr.provenance,
                "query": tr.query,
            }
        )

    def _remember_hunter_turn(ctx: str, out: SectionOutput) -> None:
        hunter_history.append({"role": "user", "content": ctx})
        reply = _strip_think_tags(out.raw)[:_hunter_history_turn_cap_chars]
        hunter_history.append({"role": "assistant", "content": reply})
        cap = _hunter_history_cap_pairs * 2
        if len(hunter_history) > cap:
            del hunter_history[: len(hunter_history) - cap]

    while not _budget_exhausted():
        if not hunter_history:
            ctx = format_for_reasoning(tool_results, trigger)
        else:
            ctx = format_new_evidence(new_since_last_hunt)
        hunter_out = run_reasoning_model(
            ctx,
            reasoning_model=models["reasoning"],
            ground_truth=ground_truth,
            history=hunter_history,
            dry_run=dry_run,
        )
        hunter_out = _ground_hunter_evidence(hunter_out, tool_results, ground_truth)
        hunter_out = _ground_similarity(hunter_out, tool_results)
        _remember_hunter_turn(ctx, hunter_out)
        new_since_last_hunt = []
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

        if hunter_out.technique_ids:
            consecutive_no_hypothesis_rounds = 0
        elif hunter_out.wants_more():
            consecutive_no_hypothesis_rounds += 1
        stalled = consecutive_no_hypothesis_rounds >= _hunter_stall_cap

        if hunter_out.wants_more() and not stalled:
            if _budget_exhausted():
                break
            _gather(hunter_out.request_more)
            rounds += 1
            continue

        ectx = format_for_expert(hunter_out, tool_results, trigger, hunter_history=hunter_history)
        told_expert_final_round = False
        if stalled and hunter_out.wants_more():
            # Whether a post-Expert request_more could ever actually be
            # honored: one round for the gather, plus at least one more for
            # the Hunter turn that has to process it before the Expert is
            # reachable again (the post-gather loop always returns to the
            # Hunter, never straight back to the Expert) — < 2 rounds left
            # after this Expert call means it structurally cannot happen.
            # Found live 2026-07-20 (GATE-D validation): under the *default*
            # budget (max_rounds=6, stall_cap=3) this stall-triggered
            # hand-off always lands with exactly 0 rounds left after the
            # Expert's turn — "you may still request one targeted gap" was
            # being offered on every single stalled conclusion, never once
            # actually honorable, and the Expert doing so anyway forced
            # UNRESOLVED instead of the RULED_OUT/ANOMALOUS_UNCLASSIFIED it
            # had just been told were valid to render right then.
            rounds_left_after_expert = max_rounds - (rounds + 1)
            if rounds_left_after_expert >= 2:
                ectx += (
                    f"\n\nNote: the hunter has searched {consecutive_no_hypothesis_rounds} "
                    "consecutive rounds without forming a hypothesis — repeated requests have "
                    "not surfaced anything more specific. Render your best-grounded conclusion "
                    "from what has been gathered so far; RULED_OUT or ANOMALOUS_UNCLASSIFIED are "
                    "valid, honest conclusions when nothing more specific is available. You may "
                    "still request one targeted gap if you believe it would change the outcome."
                )
            else:
                told_expert_final_round = True
                ectx += (
                    f"\n\nNote: the hunter has searched {consecutive_no_hypothesis_rounds} "
                    "consecutive rounds without forming a hypothesis, and this is the final "
                    "round available — no further evidence can be gathered regardless of what "
                    "you request. You MUST render CONFIRMED, RULED_OUT, or ANOMALOUS_UNCLASSIFIED "
                    "now, using only what has already been gathered; RULED_OUT or "
                    "ANOMALOUS_UNCLASSIFIED are valid, honest conclusions when nothing more "
                    "specific is available. Do not request more evidence."
                )
            consecutive_no_hypothesis_rounds = 0
        expert_out = run_expert_model(
            ectx,
            expert_model=models["expert"],
            ground_truth=ground_truth,
            tool_results=tool_results,
            hunter_similar_to=hunter_out.similar_to,
            dry_run=dry_run,
        )
        expert_out = _ground_similarity(expert_out, tool_results)

        # Retry-not-fabricate (same "same retry budget" discipline as
        # blue._run_blue_turn's P5-SCORING-BIAS-001): if we already told the
        # Expert plainly that this is its final turn and no more evidence is
        # coming, and it still didn't conclude, give it exactly one more
        # chance with an even more direct nudge before accepting UNRESOLVED —
        # never invent a verdict it didn't give (I8), but a model ignoring a
        # clear instruction once is not the same as it being incapable of
        # complying, and this doesn't burn any of the tool-gather round
        # budget (no new evidence is being requested).
        if told_expert_final_round and not expert_out.is_conclusion():
            retry_ctx = ectx + (
                "\n\nYou did not render a verdict. There is no more evidence available under "
                "any circumstance — repeating a request_more will not produce anything new. "
                "Choose exactly one of CONFIRMED, RULED_OUT, or ANOMALOUS_UNCLASSIFIED right "
                "now, based only on what has already been gathered above."
            )
            retry_out = run_expert_model(
                retry_ctx,
                expert_model=models["expert"],
                ground_truth=ground_truth,
                tool_results=tool_results,
                hunter_similar_to=hunter_out.similar_to,
                dry_run=dry_run,
            )
            retry_out = _ground_similarity(retry_out, tool_results)
            trace.append(
                {
                    "round": rounds,
                    "section": "expert-retry",
                    "model": models["expert"],
                    "verdict": retry_out.verdict,
                    "match_grade": retry_out.match_grade,
                    "wants_more": retry_out.wants_more(),
                }
            )
            if retry_out.is_conclusion():
                expert_out = retry_out

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


def _run_two_section(
    episode: Episode,
    *,
    models: dict[str, str],
    max_rounds: int,
    wall_clock_s: float | None,
    dry_run: bool,
) -> OrchestrationResult:
    """The 2-section ablation arm: tool + merged reasoning/expert (design
    §6.1's "V1 shape"). One generalist model hunts and concludes itself —
    no separate Hunter-proposes/expert-confirms handoff."""
    import time as _time

    ground_truth = set(episode.techniques)
    trigger = f"An alert was triggered on {episode.target_host} (scenario: {episode.scenario})."

    tool_results: list[ToolResult] = []
    trace: list[dict] = []
    rounds = 0
    started = _time.monotonic()
    merged_out: SectionOutput | None = None

    merged_history: list[dict] = []
    new_since_last_turn: list[ToolResult] = []
    _merged_history_cap_pairs = 6
    _merged_history_turn_cap_chars = 3000

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
        new_since_last_turn.append(tr)
        trace.append(
            {
                "round": rounds,
                "section": "tool",
                "model": models["tool"],
                "provenance": tr.provenance,
                "query": tr.query,
            }
        )

    def _remember_turn(ctx: str, out: SectionOutput) -> None:
        merged_history.append({"role": "user", "content": ctx})
        reply = _strip_think_tags(out.raw)[:_merged_history_turn_cap_chars]
        merged_history.append({"role": "assistant", "content": reply})
        cap = _merged_history_cap_pairs * 2
        if len(merged_history) > cap:
            del merged_history[: len(merged_history) - cap]

    while not _budget_exhausted():
        if not merged_history:
            ctx = format_for_merged(tool_results, trigger)
        else:
            ctx = format_new_evidence_merged(new_since_last_turn)
        merged_out = run_merged_model(
            ctx,
            merged_model=models["merged"],
            ground_truth=ground_truth,
            tool_results=tool_results,
            history=merged_history,
            dry_run=dry_run,
        )
        merged_out = _ground_similarity(merged_out, tool_results)
        _remember_turn(ctx, merged_out)
        new_since_last_turn = []
        trace.append(
            {
                "round": rounds,
                "section": "merged",
                "model": models["merged"],
                "verdict": merged_out.verdict,
                "match_grade": merged_out.match_grade,
                "wants_more": merged_out.wants_more(),
            }
        )
        rounds += 1

        if merged_out.is_conclusion():
            break
        if merged_out.wants_more() and not _budget_exhausted():
            _gather(merged_out.request_more)
            rounds += 1
            continue
        break

    if merged_out is not None and merged_out.is_conclusion():
        return OrchestrationResult(
            verdict=merged_out.verdict,
            technique_ids=merged_out.technique_ids,
            evidence=merged_out.evidence,
            reasoning=merged_out.reasoning,
            match_grade=merged_out.match_grade,
            similar_to=merged_out.similar_to,
            trace=trace,
            rounds=rounds,
            elapsed_s=round(_elapsed(), 2),
        )
    return OrchestrationResult(
        verdict="UNRESOLVED",
        trace=trace,
        rounds=rounds,
        elapsed_s=round(_elapsed(), 2),
    )
