"""review.judge -- a reasoning model reads one concern; code gates what it may say.

Division of labour (the compliance reading module's, and the council's): the model reads and
judges; code decides what survives.

* Reasoning is ALWAYS on (``think=True``). Suppressing it once invalidated a whole capability
  benchmark in this lab; a judge that cannot reason is not the judge being measured.
* Pull-based: the judge may ask for pivots (bounded, through an injected ``ToolBox``), the way
  an analyst pulls related events; nothing is pre-assembled for it beyond the concern itself.
* Every claim is grounded (``grounding``) or dropped. ``something`` asserted without a single
  grounded claim becomes ``unsure``.
* A real Challenger always runs and may use a different model. Asymmetry is deliberate: RAISING
  a concern is cheap (an analyst looks), SILENCING one is not. So ``nothing`` needs the
  Challenger's independent agreement; ``something`` is downgraded only by a *grounded* refutation.
  ``unsure`` is a first-class result, never an error.

The model transport is injected (``ModelClient``); production wiring uses the platform's
streaming client with the engine-specific think control. Tests use scripted clients.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import Claim, JudgeRecord, ReviewConcern, Verdict
from .grounding import GroundingReport, parse_claims, verify_claims
from .intake import IntakeResult

PROMPT_VERSION = "review-judge-v1"

SYSTEM_PROMPT = """\
You are a security analyst reviewing ONE concern raised by an automated reviewer over telemetry \
from many kinds of sources. Decide whether it is something an analyst should investigate \
("something"), ordinary activity ("nothing"), or whether you cannot tell from the evidence ("unsure").

Rules:
- Use ONLY the events listed under EVIDENCE and events you fetch with a pivot. Every event has an id \
in square brackets. Never invent events, hosts, users, commands or intent.
- Cite event ids for every claim. You may add a short verbatim quote from a cited event.
- The reviewer compares against KNOWN items. A resemblance is evidence, not proof: say how this \
differs from the known item.
- "unsure" is a valid answer. Prefer it to guessing.
- You may request ONE pivot at a time to look for related events: \
{"action":"pivot","term":"<a value to search for>","why":"<reason>"}.

Reply with ONE JSON object and nothing else. To conclude:
{"action":"conclude","verdict":"something|nothing|unsure","confidence":0.0,\
"claims":[{"text":"...","evidence_ids":["..."],"quote":"optional verbatim text"}],\
"benign_explanation":"... or null","next_pivots":["..."]}"""

CHALLENGER_PROMPT = """\
You are the challenger. Another analyst reached the conclusion shown below about the concern. Try \
to FALSIFY it using ONLY the events listed. If they said "something": look for a benign explanation \
or a contradiction. If they said "nothing": look for evidence the activity is actually concerning. \
If they were "unsure": look for what would be decisive.
Cite event ids for every objection. Reply with ONE JSON object and nothing else:
{"stance":"upheld|refuted|insufficient","objections":[{"text":"...","evidence_ids":["..."],\
"quote":"optional"}],"alternative":"... or null"}
upheld = you tried and the conclusion survives; refuted = you found grounded evidence against it; \
insufficient = the events cannot decide."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"enum": ["pivot", "conclude"]},
        "term": {"type": "string"},
        "why": {"type": "string"},
        "verdict": {"enum": ["something", "nothing", "unsure"]},
        "confidence": {"type": "number"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "quote": {"type": "string"},
                },
                "required": ["text", "evidence_ids"],
            },
        },
        "benign_explanation": {"type": ["string", "null"]},
        "next_pivots": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action"],
}

CHALLENGER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stance": {"enum": ["upheld", "refuted", "insufficient"]},
        "objections": JUDGE_SCHEMA["properties"]["claims"],
        "alternative": {"type": ["string", "null"]},
    },
    "required": ["stance"],
}


def prompt_digest() -> str:
    """Fingerprint of every prompt and schema; recorded in the evaluation stamp."""
    text = json.dumps(
        [PROMPT_VERSION, SYSTEM_PROMPT, CHALLENGER_PROMPT, JUDGE_SCHEMA, CHALLENGER_SCHEMA],
        sort_keys=True,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ModelReply:
    text: str
    reasoning: str = ""
    error: str = ""


class ModelClient(Protocol):
    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str,
        schema: Mapping[str, Any] | None,
        max_tokens: int,
        think: bool,
    ) -> ModelReply: ...


class ToolBox(Protocol):
    def pivot(self, term: str) -> Sequence[tuple[str, str]]:
        """``(event_id, rendered text)`` for events related to ``term`` within the window."""
        ...


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$")


def _balanced_slice(body: str, start: int) -> str | None:
    """The brace-balanced ``{...}`` beginning at ``start`` (strings and escapes respected)."""
    depth, in_str, escaped = 0, False, False
    for pos in range(start, len(body)):
        ch = body[pos]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return body[start : pos + 1]
    return None


def parse_json_object(text: str) -> dict[str, Any] | None:
    """The first JSON object in a model reply (fences and ``<think>`` blocks tolerated)."""
    body = _FENCE.sub("", _THINK_BLOCK.sub("", text).strip()).strip()
    try:
        whole = json.loads(body)
    except json.JSONDecodeError:
        whole = None
    if isinstance(whole, dict):
        return whole
    start = body.find("{")
    while start != -1:
        piece = _balanced_slice(body, start)
        if piece is not None:
            try:
                found = json.loads(piece)
            except json.JSONDecodeError:
                found = None
            if isinstance(found, dict):
                return found
        start = body.find("{", start + 1)
    return None


def render_case(
    concern: ReviewConcern, window: IntakeResult, *, max_events: int
) -> tuple[str, dict[str, str], int]:
    """The case text, the registry of citable events (id -> text) and the events available."""
    views = [window.events[e.event_id] for e in concern.evidence if e.event_id in window.events]
    views.sort(key=lambda v: (v.time is None, v.time or 0.0, v.event_id))
    shown = views[:max_events]
    registry = {v.event_id: v.text for v in shown}
    lines = [
        "CONCERN",
        f"level: {concern.level}; sources: {', '.join(concern.source_ids)}; "
        f"events: {len(views)}; span: "
        f"{'unknown' if concern.span_seconds is None else f'{concern.span_seconds:.0f}s'}",
        f"reviewer outcome: {concern.outcome.value} "
        f"(channels: {', '.join(c.value for c in concern.channels)}; "
        f"calibrated p: {concern.priority_p:.3g})",
    ]
    if concern.resembles:
        lines.append("RESEMBLES (known items)")
        for r in concern.resembles:
            lines.append(
                f"- {r.anchor_label} ({r.anchor_kind}, malice={r.malice}) similarity "
                f"{r.similarity:.2f}, p={r.empirical_p:.3g}; shares: "
                f"{', '.join(r.shares[:4]) or 'n/a'}; diverges: {', '.join(r.diverges[:4]) or 'n/a'}"
            )
    if concern.absence is not None:
        lines.append(f"ABSENCE: {concern.absence.statement}")
    lines.append(f"EXISTING DETECTION: {concern.defense_response.value}")
    lines.append(f"EVIDENCE (showing {len(shown)} of {len(views)}, time-ordered)")
    lines.extend(f"[{v.event_id}] {v.text}" for v in shown)
    return "\n".join(lines), registry, len(views)


def combine(judge: Verdict, stance: str, grounded_objections: int) -> tuple[Verdict, str]:
    """The verdict lattice: silencing needs agreement; raising yields only to grounded refutation."""
    if judge == Verdict.UNSURE:
        return Verdict.UNSURE, "judge unsure"
    if judge == Verdict.SOMETHING:
        if stance == "refuted" and grounded_objections > 0:
            return Verdict.UNSURE, "challenger refuted with a grounded objection"
        if stance == "upheld":
            return Verdict.SOMETHING, ""
        return Verdict.SOMETHING, f"challenger {stance or 'unavailable'}; raised anyway"
    if stance == "upheld":
        return Verdict.NOTHING, ""
    return (
        Verdict.UNSURE,
        f"'nothing' not independently upheld (challenger {stance or 'unavailable'})",
    )


def _msg(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


def _verdict(value: Any) -> Verdict:
    try:
        return Verdict(str(value).strip().lower())
    except ValueError:
        return Verdict.UNSURE


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _degraded(model: str, why: str, rounds: int, shown: int, total: int) -> JudgeRecord:
    return JudgeRecord(
        model=model,
        verdict=Verdict.UNSURE,
        rounds=rounds,
        degraded=why,
        evidence_shown=shown,
        evidence_total=total,
    )


def _challenge(
    client: ModelClient,
    model: str,
    case: str,
    verdict: Verdict,
    claims: Sequence[Claim],
    registry: Mapping[str, str],
    max_tokens: int,
) -> tuple[str, int]:
    conclusion = (
        "\n".join(f"- {c.text} [{', '.join(c.evidence_ids)}]" for c in claims) or "- (no claims)"
    )
    messages = [
        _msg("system", CHALLENGER_PROMPT),
        _msg(
            "user", f"{case}\n\nCONCLUSION UNDER CHALLENGE\nverdict: {verdict.value}\n{conclusion}"
        ),
    ]
    reply = client.complete(
        messages, model=model, schema=CHALLENGER_SCHEMA, max_tokens=max_tokens, think=True
    )
    if reply.error:
        return "", 0
    obj = parse_json_object(reply.text)
    if obj is None:
        return "", 0
    stance = str(obj.get("stance") or "").strip().lower()
    if stance not in {"upheld", "refuted", "insufficient"}:
        return "", 0
    objections, _bad = parse_claims(obj.get("objections"))
    report: GroundingReport = verify_claims(objections, registry)
    return stance, len(report.kept)


def run_judge(
    concern: ReviewConcern,
    window: IntakeResult,
    *,
    client: ModelClient,
    model: str,
    tools: ToolBox | None = None,
    challenger_model: str | None = None,
    max_rounds: int = 3,
    max_events: int = 40,
    max_tokens: int = 2048,
) -> JudgeRecord:
    """Judge one concern. ``max_*`` are budgets, recorded by the caller, not decision constants."""
    case, registry, total = render_case(concern, window, max_events=max_events)
    shown = len(registry)
    messages = [_msg("system", SYSTEM_PROMPT), _msg("user", case)]
    conclusion: dict[str, Any] | None = None
    repaired = False
    rounds = 0

    while rounds < max_rounds:
        rounds += 1
        reply = client.complete(
            messages, model=model, schema=JUDGE_SCHEMA, max_tokens=max_tokens, think=True
        )
        if reply.error:
            return _degraded(model, f"model error: {reply.error}", rounds, shown, total)
        obj = parse_json_object(reply.text)
        if obj is None:
            if repaired:
                return _degraded(model, "model returned no JSON object twice", rounds, shown, total)
            repaired = True
            messages += [
                _msg("assistant", reply.text),
                _msg(
                    "user",
                    "Your reply was not a single JSON object. Reply with ONE JSON object only.",
                ),
            ]
            continue
        if obj.get("action") == "pivot":
            if tools is None or rounds >= max_rounds:
                messages += [
                    _msg("assistant", reply.text),
                    _msg("user", "No pivot is available. Conclude now."),
                ]
                continue
            term = str(obj.get("term") or "").strip()
            found = tools.pivot(term) if term else []
            fresh = [(i, t) for i, t in found if i not in registry]
            registry.update(dict(fresh))
            listing = "\n".join(f"[{i}] {t}" for i, t in fresh[:max_events]) or "no new events"
            messages += [
                _msg("assistant", reply.text),
                _msg("user", f"PIVOT RESULT for {term!r}:\n{listing}"),
            ]
            continue
        conclusion = obj
        break

    if conclusion is None:
        return _degraded(model, "no conclusion within the round budget", rounds, shown, total)

    verdict = _verdict(conclusion.get("verdict"))
    claims, malformed = parse_claims(conclusion.get("claims"))
    grounding = verify_claims(claims, registry)
    notes: list[str] = []
    if verdict == Verdict.SOMETHING and not grounding.kept:
        verdict = Verdict.UNSURE
        notes.append("'something' asserted without a grounded claim")

    stance, grounded_objections = _challenge(
        client, challenger_model or model, case, verdict, grounding.kept, registry, max_tokens
    )
    final, why = combine(verdict, stance, grounded_objections)
    if why:
        notes.append(why)
    return JudgeRecord(
        model=model,
        verdict=final,
        confidence=_clamp(conclusion.get("confidence")),
        claims=grounding.kept,
        dropped_claims=len(grounding.dropped) + malformed,
        challenger_verdict=stance or "unavailable",
        rounds=rounds,
        note="; ".join(notes),
        evidence_shown=shown,
        evidence_total=total,
    )
