"""Evidence-backed, isolated multi-model review for Council workspaces.

Council Review is deliberately separate from the sequential ``chain`` path:
reviewers receive the same review material but never see one another's output.
They return a small JSON contract, code computes participation/quorum over the
full roster, and only then may a synthesizer explain the deterministic result.

``council.speed`` can shorten a run. Every flag defaults off, which is today's
parallel three-reviewer council. ``early_quorum`` stops once the coded rule
can no longer change. ``single_model`` keeps each role's prompt and a separate
call, on one resident model. ``progress`` streams a verdict line per seat
before synthesis. ``decompose`` settles obvious claims on a small model and
sends only the unsettled ones to the big seats. An authenticated request
may override that block for one call with ``portal_council_config``.
"""

from __future__ import annotations

import asyncio
import copy
import itertools
import json
import logging
import math
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
from typing import Any

import httpx

from portal.platform.inference.model_cards import card_sampling

logger = logging.getLogger(__name__)
_STREAM_HEARTBEAT_S = 15.0

_http_client: httpx.AsyncClient | None = None

_RECOMMENDATIONS = frozenset({"SUPPORT", "REVISE", "REJECT", "ABSTAIN"})
_DECISIONS = frozenset({"SUPPORT", "REVISE", "REJECT", "ESCALATE"})


def _apply_think(payload: dict[str, Any], think: bool | str | None, backend_type: str) -> None:
    """Set the think control in whatever field the target engine actually reads.

    Council payloads are built and posted directly to ``backend.chat_url``
    (this module skips the pipeline's own ``_inject_omlx_options`` /
    ``_inject_ollama_options`` translation entirely — see the module docstring
    on why that's a known gap). A bare ``"think"`` key is correct for Ollama's
    native ``/api/chat`` but oMLX ignores it silently: no error, no
    ``reasoning_content`` field, and the model still reasons — straight into
    ``content``, corrupting the JSON this council depends on. Verified live
    2026-09-26 (a bare ``think:false`` to oMLX's DeepSeek-R1 conversion left
    the chain-of-thought unsuppressed in ``content``). oMLX reads
    ``chat_template_kwargs.enable_thinking`` instead — the same mapping
    ``_inject_omlx_options`` already uses for ordinary chat completions.
    """
    if think is None:
        return
    if backend_type == "omlx":
        ctk = dict(payload.get("chat_template_kwargs") or {})
        ctk["enable_thinking"] = think
        payload["chat_template_kwargs"] = ctk
    else:
        payload["think"] = think


_REVIEW_CONTRACT = """
Return exactly one JSON object and no Markdown:
{
  "recommendation": "SUPPORT|REVISE|REJECT|ABSTAIN",
  "confidence": 0.0,
  "findings": [
    {
      "claim": "specific finding",
      "severity": "high|medium|low",
      "evidence": ["exact evidence reference from the review material"],
      "action": "specific corrective action"
    }
  ],
  "missing_evidence": ["information needed before a stronger conclusion"],
  "strongest_objection": "best case against your recommendation",
  "conditions_to_change": ["what would change your recommendation"]
}

- Work independently. You cannot see other reviewers' answers.
- Use only the supplied review material. Do not invent repository state, test
  results, citations, requirements, or user constraints.
- Every substantive finding must identify its evidence.
- SUPPORT: proceed as proposed; any findings are minor.
- REVISE: the goal is sound and the proposal can proceed once named, specific changes are made.
- REJECT: should not proceed in this form; the premise is wrong, the risk outweighs the benefit,
  or no revision of this proposal fixes the core problem.
- ABSTAIN: the material is insufficient for your assigned review.
- Choose the recommendation that follows from your own highest-severity finding.
- Prefer a few actionable findings over generic commentary.
""".strip()

_SYNTHESIS_CONTRACT = """
You are Portal Council Review's synthesizer. Code has already determined the
decision from the full configured roster. You may explain that decision, but
you MUST NOT change it.

Use only the supplied review material and validated reviewer records. Do not
invent claims or evidence. Attribute material findings to reviewer ids. Preserve
meaningful dissent and missing evidence.

Return concise Markdown with exactly these headings:
## Recommendation
## Evidence and findings
## Strongest objection
## Missing evidence
## Conditions that would change the recommendation
## Next actions
""".strip()


@dataclass
class CouncilOpinion:
    """One configured seat's parsed response, including non-participation."""

    member_id: str
    label: str
    model: str
    recommendation: str = "ABSTAIN"
    confidence: float = 0.0
    findings: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    strongest_objection: str = ""
    conditions_to_change: list[str] = field(default_factory=list)
    valid: bool = False
    error: str = ""
    # A skipped seat is recorded and is never a vote. Early quorum and a fully
    # settled decompose pass set this; a failed reviewer does not.
    skipped: bool = False
    skip_reason: str = ""

    @property
    def participated(self) -> bool:
        """A valid ABSTAIN remains visible but does not cast a decision vote."""
        return self.valid and self.recommendation != "ABSTAIN" and not self.skipped


@dataclass
class CouncilAggregate:
    """Deterministic decision over the full configured reviewer roster."""

    decision: str
    participation: float
    participating: int
    roster: int
    required_participation: int
    required_votes: int
    votes: dict[str, int]
    dissent: list[str]
    rationale: str
    # "quorum" is the coded vote. "decompose" means no big-model vote was cast.
    decision_source: str = "quorum"


@dataclass
class CouncilCompletion:
    """OpenAI-compatible completion plus route information for response headers."""

    data: dict[str, Any]
    backend_id: str
    model: str


def _json_object(text: str) -> dict[str, Any] | None:
    """Extract one JSON object from plain text or a fenced model response."""
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def parse_opinion(member: dict[str, Any], text: str, *, error: str = "") -> CouncilOpinion:
    """Parse and normalize one reviewer response without treating failure as a vote."""
    base = CouncilOpinion(
        member_id=str(member.get("id", "")),
        label=str(member.get("label", member.get("id", ""))),
        model=str(member.get("model", "")),
        error=error,
    )
    if error:
        return base

    payload = _json_object(text)
    if payload is None:
        base.error = "reviewer did not return a JSON object"
        return base

    recommendation = str(payload.get("recommendation", "")).upper()
    if recommendation not in _RECOMMENDATIONS:
        base.error = "reviewer returned an invalid recommendation"
        return base

    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    findings = payload.get("findings")
    missing = payload.get("missing_evidence")
    conditions = payload.get("conditions_to_change")
    base.recommendation = recommendation
    base.confidence = confidence
    base.findings = (
        [item for item in findings if isinstance(item, dict)] if isinstance(findings, list) else []
    )
    base.missing_evidence = [str(item) for item in missing] if isinstance(missing, list) else []
    base.strongest_objection = str(payload.get("strongest_objection", ""))
    base.conditions_to_change = (
        [str(item) for item in conditions] if isinstance(conditions, list) else []
    )
    base.valid = True
    return base


def aggregate_opinions(
    opinions: list[CouncilOpinion],
    *,
    minimum_participation: float,
    quorum: float,
) -> CouncilAggregate:
    """Compute the decision over the full roster; non-voters never shrink it."""
    roster = len(opinions)
    participating = sum(opinion.participated for opinion in opinions)
    participation = participating / roster if roster else 0.0
    required_participation = math.ceil((minimum_participation * roster) - 1e-9)
    required_votes = math.ceil((quorum * roster) - 1e-9)
    counts = Counter(opinion.recommendation for opinion in opinions if opinion.participated)
    votes = {name: counts.get(name, 0) for name in ("SUPPORT", "REVISE", "REJECT")}

    if roster == 0 or participating < required_participation:
        decision = "ESCALATE"
        rationale = (
            f"participation {participating}/{roster} below required "
            f"{required_participation}/{roster}"
        )
    else:
        top_count = max(votes.values(), default=0)
        leaders = [name for name, count in votes.items() if count == top_count and count > 0]
        if len(leaders) == 1 and top_count >= required_votes:
            decision = leaders[0]
            rationale = f"{decision} reached {top_count}/{roster} votes"
        else:
            decision = "ESCALATE"
            rationale = f"no recommendation reached the required {required_votes}/{roster} votes"

    assert decision in _DECISIONS
    dissent = [
        opinion.member_id
        for opinion in opinions
        if opinion.participated and opinion.recommendation != decision
    ]
    return CouncilAggregate(
        decision=decision,
        participation=round(participation, 3),
        participating=participating,
        roster=roster,
        required_participation=required_participation,
        required_votes=required_votes,
        votes=votes,
        dissent=dissent,
        rationale=rationale,
    )


_CHECK_VALUES = frozenset({"yes", "no", "unsure"})
_DECOMPOSE_MAX_TOKENS = 1024
# 4^6 is 4096 hypothetical rosters. Larger tails just run; production is 3 seats.
_EARLY_QUORUM_SIM_LIMIT = 6

_DECOMPOSE_CONTRACT = """
Split the submission into distinct material claims. For each claim answer three
checks using only the submission. Return exactly one JSON object and no Markdown:
{"claims": [
  {"claim": "one claim", "evidence_present": "yes|no|unsure",
   "contradicted": "yes|no|unsure", "stale": "yes|no|unsure",
   "evidence": "short quote from the submission, or empty"}
]}
Use unsure when the submission does not say. Do not invent repository state,
test results, or citations.
""".strip()


def _speed_flags(council: dict[str, Any]) -> dict[str, Any]:
    """Read speed flags. Missing block means every mode is off."""
    raw = council.get("speed") if isinstance(council.get("speed"), dict) else {}
    return {
        "early_quorum": bool(raw.get("early_quorum", False)),
        "single_model": bool(raw.get("single_model", False)),
        "resident_model": str(raw.get("resident_model") or ""),
        "progress": bool(raw.get("progress", False)),
        "decompose": bool(raw.get("decompose", False)),
        "decompose_model": str(raw.get("decompose_model") or ""),
    }


def _seat_members(council: dict[str, Any], speed: dict[str, Any]) -> list[dict[str, Any]]:
    """Copy the roster. single_model rewrites the model and keeps each role."""
    members = [dict(member) for member in council.get("members") or []]
    if speed["single_model"]:
        model = speed["resident_model"] or str(council.get("synthesizer_model") or "")
        for member in members:
            member["model"] = model
    return members


def _workspace_think(workspace_id: str) -> bool | str | None:
    from portal.platform.inference.router.workspaces import WORKSPACES  # noqa: PLC0415

    return WORKSPACES.get(workspace_id, {}).get("think")


def _seat_predict(
    member: dict[str, Any], council: dict[str, Any], workspace_id: str
) -> tuple[int, bool | str | None]:
    """Answer budget, plus the thinking budget only when the seat is thinking."""
    if member.get("max_tokens") is not None:
        answer = int(member["max_tokens"])
    else:
        answer = int(council.get("reviewer_max_tokens", 4096))
    if member.get("think") is not None:
        think: bool | str | None = member.get("think")
    else:
        think = _workspace_think(workspace_id)
    reasoning = int(member.get("reasoning_max_tokens") or 0)
    if think:
        answer += reasoning
    return answer, think


_COUNCIL_SAMPLING_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "presence_penalty",
    "repeat_penalty",
)


def _seat_sampling(
    model: str, think: bool | str | None, member: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Card sampling for this thinking state, with explicit seat values on top."""
    sampling = {
        key: value
        for key, value in card_sampling(model, think).items()
        if key in _COUNCIL_SAMPLING_KEYS and value is not None
    }
    for key in _COUNCIL_SAMPLING_KEYS:
        value = (member or {}).get(key)
        if value is not None:
            sampling[key] = value
    repetition_penalty = (member or {}).get("repetition_penalty")
    if repetition_penalty is not None:
        sampling["repeat_penalty"] = repetition_penalty
    return sampling


def _skipped_opinion(member: dict[str, Any], reason: str) -> CouncilOpinion:
    return CouncilOpinion(
        member_id=str(member.get("id", "")),
        label=str(member.get("label", member.get("id", ""))),
        model=str(member.get("model", "")),
        skipped=True,
        skip_reason=reason,
    )


def votes_decide_outcome(
    opinions: list[CouncilOpinion],
    *,
    remaining: int,
    minimum_participation: float,
    quorum: float,
) -> str | None:
    """The coded decision if every completion of the tail agrees, else None.

    Remaining seats are simulated as SUPPORT, REVISE, REJECT, or a non-vote.
    The caller may skip them only when that set has one decision. Skipping
    records those seats as non-votes, which is one of the simulated completions,
    so the final aggregate matches the locked decision.
    """
    if remaining <= 0:
        return aggregate_opinions(
            opinions,
            minimum_participation=minimum_participation,
            quorum=quorum,
        ).decision
    if remaining > _EARLY_QUORUM_SIM_LIMIT:
        return None
    locked: str | None = None
    for combo in itertools.product(("SUPPORT", "REVISE", "REJECT", "ABSTAIN"), repeat=remaining):
        hypothetical = list(opinions)
        for index, vote in enumerate(combo):
            valid = vote != "ABSTAIN"
            hypothetical.append(
                CouncilOpinion(
                    member_id=f"_remaining_{index}",
                    label="",
                    model="",
                    recommendation=vote if valid else "ABSTAIN",
                    valid=valid,
                )
            )
        decision = aggregate_opinions(
            hypothetical,
            minimum_participation=minimum_participation,
            quorum=quorum,
        ).decision
        if locked is None:
            locked = decision
        elif decision != locked:
            return None
    return locked


def claim_disposition(claim: dict[str, Any]) -> str:
    """Settle one small-model claim, or send it upstairs.

    ``unsure`` and check combinations that disagree (evidence that is also
    contradicted, a contradiction that is also stale, a missing quote that is
    also contradicted or stale) escalate. A consistent answer settles.
    """
    present = str(claim.get("evidence_present") or "")
    contradicted = str(claim.get("contradicted") or "")
    stale = str(claim.get("stale") or "")
    if any(value not in _CHECK_VALUES for value in (present, contradicted, stale)):
        return "escalate"
    if "unsure" in (present, contradicted, stale):
        return "escalate"
    if present == "yes" and contradicted == "yes":
        return "escalate"
    if contradicted == "yes" and stale == "yes":
        return "escalate"
    if present == "no" and contradicted == "yes":
        return "escalate"
    if present == "no" and stale == "yes":
        return "escalate"
    if contradicted == "yes":
        return "contradicted"
    if stale == "yes":
        return "stale"
    if present == "no":
        return "missing"
    if present == "yes":
        return "supported"
    return "escalate"


def decision_from_settled(dispositions: list[str]) -> str:
    """Code decision for a claim sheet the big models will not vote on."""
    if not dispositions or any(item == "escalate" for item in dispositions):
        return "ESCALATE"
    if all(item == "contradicted" for item in dispositions):
        return "REJECT"
    if any(item == "contradicted" for item in dispositions):
        return "REVISE"
    if any(item in ("stale", "missing") for item in dispositions):
        return "REVISE"
    if all(item == "supported" for item in dispositions):
        return "SUPPORT"
    return "ESCALATE"


def parse_claim_checks(text: str) -> list[dict[str, Any]] | None:
    """Parse the small model's claim sheet. None means fall back to a full review."""
    payload = _json_object(text)
    if payload is None:
        return None
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return None
    parsed: list[dict[str, Any]] = []
    for item in claims:
        if not isinstance(item, dict):
            return None
        claim = str(item.get("claim") or "").strip()
        if not claim:
            return None
        parsed.append(
            {
                "claim": claim,
                "evidence_present": str(item.get("evidence_present") or "").strip().lower(),
                "contradicted": str(item.get("contradicted") or "").strip().lower(),
                "stale": str(item.get("stale") or "").strip().lower(),
                "evidence": str(item.get("evidence") or ""),
            }
        )
    return parsed


def _cold_load_s(data: dict[str, Any]) -> float | None:
    """Seconds of engine model-load time. Ollama's native field is nanoseconds."""
    explicit = data.get("portal_timings") if isinstance(data.get("portal_timings"), dict) else {}
    if explicit.get("load_s") is not None:
        try:
            return round(float(explicit["load_s"]), 6)
        except (TypeError, ValueError):
            pass
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    if usage.get("load_s") is not None:
        try:
            return round(float(usage["load_s"]), 6)
        except (TypeError, ValueError):
            pass
    raw = data.get("load_duration")
    if raw is None:
        raw = usage.get("load_duration_ns")
    try:
        nanoseconds = float(raw)
    except (TypeError, ValueError):
        return None
    if nanoseconds < 0:
        return None
    return round(nanoseconds / 1_000_000_000, 6)


def _stage_timing(
    stage: str,
    kind: str,
    model: str,
    data: dict[str, Any] | None,
    *,
    skipped: bool,
    called: bool,
    skip_reason: str = "",
) -> dict[str, Any]:
    """One seat or the synthesizer, using ``normalize_engine_timings`` for the engine."""
    from portal.platform.inference.router.trace import normalize_engine_timings  # noqa: PLC0415

    empty: dict[str, Any] = {
        "stage": stage,
        "kind": kind,
        "model": model,
        "skipped": skipped,
        "called": called,
        "skip_reason": skip_reason,
        "cold_load_s": None,
        "prefill_s": None,
        "decode_s": None,
        "tokens": None,
        "portal_timings": {},
    }
    if skipped or not data:
        return empty
    timings = normalize_engine_timings(data)
    answer_s = timings.get("answer_s")
    reasoning_s = timings.get("reasoning_s")
    decode_s = None
    if answer_s is not None or reasoning_s is not None:
        decode_s = round((answer_s or 0.0) + (reasoning_s or 0.0), 6)
    answer_tokens = timings.get("answer_tokens")
    reasoning_tokens = timings.get("reasoning_tokens")
    tokens = None
    if answer_tokens is not None or reasoning_tokens is not None:
        tokens = int(answer_tokens or 0) + int(reasoning_tokens or 0)
    empty.update(
        {
            "cold_load_s": _cold_load_s(data),
            "prefill_s": timings.get("prefill_s"),
            "decode_s": decode_s,
            "tokens": tokens,
            "portal_timings": timings,
        }
    )
    return empty


def _span_stage(stage: dict[str, Any]) -> None:
    from portal.platform.inference.router.trace import span as trace_span  # noqa: PLC0415

    trace_span(
        "council.stage",
        stage=stage["stage"],
        kind=stage["kind"],
        model=stage["model"],
        skipped=stage["skipped"],
        called=stage["called"],
        skip_reason=stage["skip_reason"],
        cold_load_s=stage["cold_load_s"],
        prefill_s=stage["prefill_s"],
        decode_s=stage["decode_s"],
        tokens=stage["tokens"],
    )


def _verdict_line(opinion: CouncilOpinion) -> str:
    if opinion.skipped:
        return f"**{opinion.label}:** skipped ({opinion.skip_reason}).\n\n"
    if not opinion.valid:
        detail = opinion.error or "invalid"
        return f"**{opinion.label}:** no vote ({detail}).\n\n"
    return (
        f"**{opinion.label}:** {opinion.recommendation} (confidence {opinion.confidence:.2f}).\n\n"
    )


def _message_text(data: dict[str, Any]) -> str:
    """Return only the model's answer channel; thoughts are never votes."""
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _render_review_material(messages: list[dict[str, Any]]) -> str:
    """Flatten conversation context so reviewer prompts cannot inherit tool state."""
    rendered: list[str] = []
    for message in messages:
        role = str(message.get("role", "unknown")).upper()
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)
        if content:
            rendered.append(f"### {role}\n{content}")
    return "\n\n".join(rendered)


def _backend_for_model(registry: Any, workspace_id: str, model: str) -> Any | None:
    """Find a healthy backend that explicitly declares ``model``."""
    ordered = registry.get_backend_candidates(workspace_id)
    seen = {backend.id for backend in ordered}
    ordered.extend(
        backend for backend in registry.list_healthy_backends() if backend.id not in seen
    )
    return next((backend for backend in ordered if model in backend.models), None)


@dataclass
class _EngineCall:
    """One backend chat completion, plus the raw body the timings are read from."""

    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    called: bool = False
    backend_id: str = "council"
    error: str = ""


async def _post_model(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    sampling: dict[str, Any],
    think: bool | str | None,
    workspace_id: str,
    registry: Any,
    role: str,
) -> _EngineCall:
    """Post one isolated chat completion. Council never streams the engine call."""
    if _http_client is None:
        return _EngineCall(error="pipeline HTTP client is not initialized")
    backend = _backend_for_model(registry, workspace_id, model)
    if backend is None or not model:
        return _EngineCall(error=f"configured model is unavailable: {model}")
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    payload.update(sampling)
    if backend.type == "omlx" and "repeat_penalty" in sampling:
        payload["repetition_penalty"] = sampling["repeat_penalty"]
    _apply_think(payload, think, backend.type)
    try:
        response = await _http_client.post(backend.chat_url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            data = {}
        return _EngineCall(
            text=_message_text(data),
            data=data,
            called=True,
            backend_id=str(backend.id),
        )
    except Exception as exc:
        logger.warning(
            "Council %s failed: workspace=%s model=%s error=%s",
            role,
            workspace_id,
            model,
            type(exc).__name__,
        )
        return _EngineCall(backend_id=str(backend.id), error=f"{type(exc).__name__}: {exc}")


async def _call_reviewer(
    member: dict[str, Any],
    *,
    review_material: str,
    workspace_id: str,
    registry: Any,
    council: dict[str, Any],
) -> tuple[CouncilOpinion, _EngineCall]:
    model = str(member.get("model", ""))
    if _http_client is None:
        return (
            parse_opinion(member, "", error="pipeline HTTP client is not initialized"),
            _EngineCall(error="pipeline HTTP client is not initialized"),
        )
    backend = _backend_for_model(registry, workspace_id, model)
    if backend is None:
        error = f"configured model is unavailable: {model}"
        return parse_opinion(member, "", error=error), _EngineCall(error=error)

    # A thinking-capable model can spend the whole budget reasoning, returning
    # an empty opinion. Per-seat think overrides the workspace flag.
    system = f"{member.get('system', '')}\n\n{_REVIEW_CONTRACT}".strip()
    max_tokens, think = _seat_predict(member, council, workspace_id)
    result = await _post_model(
        model=model,
        system=system,
        user=f"## REVIEW MATERIAL\n\n{review_material}",
        max_tokens=max_tokens,
        sampling=_seat_sampling(model, think, member),
        think=think,
        workspace_id=workspace_id,
        registry=registry,
        role=f"reviewer {member.get('id')}",
    )
    if result.error:
        return parse_opinion(member, "", error=result.error), result
    return parse_opinion(member, result.text), result


def _fallback_markdown(
    aggregate: CouncilAggregate,
    opinions: list[CouncilOpinion],
    settled: list[dict[str, Any]] | None = None,
) -> str:
    """Auditable result when the optional narrative synthesizer is unavailable."""
    findings: list[str] = []
    missing: list[str] = []
    objections: list[str] = []
    conditions: list[str] = []
    for opinion in opinions:
        for finding in opinion.findings:
            claim = str(finding.get("claim", "")).strip()
            evidence = finding.get("evidence") or []
            action = str(finding.get("action", "")).strip()
            if claim:
                suffix = f" Evidence: {', '.join(map(str, evidence))}." if evidence else ""
                if action:
                    suffix += f" Action: {action}."
                findings.append(f"- **{opinion.member_id}:** {claim}.{suffix}")
        missing.extend(f"- **{opinion.member_id}:** {item}" for item in opinion.missing_evidence)
        if opinion.strongest_objection:
            objections.append(f"- **{opinion.member_id}:** {opinion.strongest_objection}")
        conditions.extend(
            f"- **{opinion.member_id}:** {item}" for item in opinion.conditions_to_change
        )
    for item in settled or []:
        claim = str(item.get("claim") or "").strip()
        disposition = str(item.get("disposition") or "").strip()
        if claim:
            findings.append(f"- **decompose:** {claim} ({disposition}).")

    return "\n\n".join(
        [
            "## Recommendation\n"
            f"**{aggregate.decision}** — {aggregate.rationale}. "
            f"Participation: {aggregate.participating}/{aggregate.roster}.",
            "## Evidence and findings\n" + ("\n".join(findings) or "- No validated findings."),
            "## Strongest objection\n" + ("\n".join(objections) or "- None supplied."),
            "## Missing evidence\n" + ("\n".join(missing) or "- None supplied."),
            "## Conditions that would change the recommendation\n"
            + ("\n".join(conditions) or "- None supplied."),
            "## Next actions\n"
            "- Resolve high-severity findings and missing evidence, then rerun the review.",
        ]
    )


async def _synthesize(
    *,
    council: dict[str, Any],
    aggregate: CouncilAggregate,
    opinions: list[CouncilOpinion],
    review_material: str,
    workspace_id: str,
    registry: Any,
    settled: list[dict[str, Any]] | None = None,
) -> tuple[str, _EngineCall]:
    model = str(council.get("synthesizer_model", ""))
    records = [asdict(opinion) for opinion in opinions]
    synthesis_packet: dict[str, Any] = {
        "code_determined_decision": asdict(aggregate),
        "reviewers": records,
    }
    if settled:
        synthesis_packet["settled_claims"] = settled
    think = council.get("synthesizer_think", _workspace_think(workspace_id))
    result = await _post_model(
        model=model,
        system=_SYNTHESIS_CONTRACT,
        user=(
            f"## ORIGINAL REVIEW MATERIAL\n\n{review_material}\n\n"
            "## VALIDATED COUNCIL PACKET\n\n"
            f"{json.dumps(synthesis_packet, ensure_ascii=False)}"
        ),
        max_tokens=int(council.get("synthesizer_max_tokens", 4096)),
        sampling=_seat_sampling(model, think),
        think=think,
        workspace_id=workspace_id,
        registry=registry,
        role="synthesizer",
    )
    text = result.text.strip()
    if result.called and text:
        # The machine decision is always rendered first, even if a weak
        # synthesizer later writes contradictory prose.
        prefix = (
            f"**Code-determined decision: {aggregate.decision}**  \n"
            f"Participation: {aggregate.participating}/{aggregate.roster}; "
            f"votes: {aggregate.votes}.\n\n"
        )
        return prefix + text, result
    return _fallback_markdown(aggregate, opinions, settled), result


def _remember(
    stages: list[dict[str, Any]],
    stage: dict[str, Any],
) -> None:
    stages.append(stage)
    _span_stage(stage)


def _recorded_speed(speed: dict[str, Any], council: dict[str, Any]) -> dict[str, Any]:
    resident = ""
    if speed["single_model"]:
        resident = speed["resident_model"] or str(council.get("synthesizer_model") or "")
    return {
        "early_quorum": speed["early_quorum"],
        "single_model": speed["single_model"],
        "resident_model": resident,
        "progress": speed["progress"],
        "decompose": speed["decompose"],
        "decompose_model": speed["decompose_model"] if speed["decompose"] else "",
    }


def _decompose_aggregate(
    decision: str,
    roster: int,
    *,
    minimum_participation: float,
    quorum: float,
    settled_count: int,
) -> CouncilAggregate:
    required_participation = math.ceil((minimum_participation * roster) - 1e-9) if roster else 0
    required_votes = math.ceil((quorum * roster) - 1e-9) if roster else 0
    return CouncilAggregate(
        decision=decision,
        participation=0.0,
        participating=0,
        roster=roster,
        required_participation=required_participation,
        required_votes=required_votes,
        votes={"SUPPORT": 0, "REVISE": 0, "REJECT": 0},
        dissent=[],
        rationale=(
            f"decompose settled {settled_count} claims as {decision} without a big-model vote"
        ),
        decision_source="decompose",
    )


def _merge_settled(
    aggregate: CouncilAggregate,
    opinions: list[CouncilOpinion],
    settled: list[dict[str, Any]],
) -> CouncilAggregate:
    """A settled defect sticks. Unresolved big-model claims still escalate."""
    if not settled or aggregate.decision == "ESCALATE":
        return aggregate
    settled_decision = decision_from_settled(
        [str(item.get("disposition") or "") for item in settled]
    )
    rank = {"SUPPORT": 0, "REVISE": 1, "REJECT": 2}
    if settled_decision not in rank or rank[settled_decision] <= rank.get(aggregate.decision, 0):
        return aggregate
    dissent = [
        opinion.member_id
        for opinion in opinions
        if opinion.participated and opinion.recommendation != settled_decision
    ]
    return replace(
        aggregate,
        decision=settled_decision,
        dissent=dissent,
        decision_source="decompose+quorum",
        rationale=f"{aggregate.rationale}; settled claims require {settled_decision}",
    )


def _escalated_material(claims: list[dict[str, Any]]) -> str:
    lines = [
        "## CLAIMS TO REVIEW",
        "Review only these unsettled claims. Do not re-open claims that are absent here.",
    ]
    for claim in claims:
        lines.append(f"- {claim.get('claim', '')}")
        evidence = str(claim.get("evidence") or "").strip()
        if evidence:
            lines.append(f"  evidence: {evidence}")
    return "\n".join(lines)


async def _run_decompose(
    *,
    speed: dict[str, Any],
    review_material: str,
    workspace_id: str,
    registry: Any,
    stages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return seat material, settled claims, and escalated claims.

    A broken sheet, or a sheet where every claim escalates, reviews the
    original submission. Settled claims do not go to the big seats.
    """
    model = speed["decompose_model"]
    result = await _post_model(
        model=model,
        system=_DECOMPOSE_CONTRACT,
        user=f"## SUBMISSION\n\n{review_material}",
        max_tokens=_DECOMPOSE_MAX_TOKENS,
        sampling={"temperature": 0.0},
        think=False,
        workspace_id=workspace_id,
        registry=registry,
        role="decompose",
    )
    _remember(
        stages,
        _stage_timing(
            "decompose",
            "decompose",
            model,
            result.data if result.called else None,
            skipped=False,
            called=result.called,
        ),
    )
    parsed = parse_claim_checks(result.text) if result.called and not result.error else None
    if parsed is None:
        return review_material, [], []
    settled: list[dict[str, Any]] = []
    escalated: list[dict[str, Any]] = []
    for claim in parsed:
        disposition = claim_disposition(claim)
        annotated = {**claim, "disposition": disposition}
        if disposition == "escalate":
            escalated.append(annotated)
        else:
            settled.append(annotated)
    if escalated and not settled:
        return review_material, [], escalated
    if not escalated:
        return review_material, settled, []
    return _escalated_material(escalated), settled, escalated


async def _notify_seat(
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None,
    opinion: CouncilOpinion,
) -> None:
    if on_seat is not None:
        await on_seat(opinion)


async def _skip_members(
    members: list[dict[str, Any]],
    reason: str,
    stages: list[dict[str, Any]],
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None,
) -> list[CouncilOpinion]:
    opinions: list[CouncilOpinion] = []
    for member in members:
        opinion = _skipped_opinion(member, reason)
        opinions.append(opinion)
        _remember(
            stages,
            _stage_timing(
                opinion.member_id,
                "seat",
                opinion.model,
                None,
                skipped=True,
                called=False,
                skip_reason=reason,
            ),
        )
        await _notify_seat(on_seat, opinion)
    return opinions


async def _review_one(
    member: dict[str, Any],
    *,
    review_material: str,
    workspace_id: str,
    registry: Any,
    council: dict[str, Any],
) -> tuple[CouncilOpinion, dict[str, Any]]:
    opinion, result = await _call_reviewer(
        member,
        review_material=review_material,
        workspace_id=workspace_id,
        registry=registry,
        council=council,
    )
    stage = _stage_timing(
        opinion.member_id,
        "seat",
        opinion.model,
        result.data if result.called else None,
        skipped=False,
        called=result.called,
    )
    # Span at completion so a parallel seat's at_ms is the real finish time.
    _span_stage(stage)
    return opinion, stage


async def _collect_parallel(
    members: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None,
    review_one: Callable[[dict[str, Any]], Awaitable[tuple[CouncilOpinion, dict[str, Any]]]],
) -> list[CouncilOpinion]:
    """Today's path: gather, unless progress needs a line as each seat finishes."""
    if on_seat is None:
        pairs = list(await asyncio.gather(*[review_one(member) for member in members]))
    else:
        tasks = [asyncio.create_task(review_one(member)) for member in members]
        done: dict[str, tuple[CouncilOpinion, dict[str, Any]]] = {}
        for finished in asyncio.as_completed(tasks):
            opinion, stage = await finished
            done[opinion.member_id] = (opinion, stage)
            await on_seat(opinion)
        pairs = [done[str(member.get("id", ""))] for member in members]
    opinions: list[CouncilOpinion] = []
    for opinion, stage in pairs:
        opinions.append(opinion)
        stages.append(stage)
    return opinions


async def _collect_until_locked(
    members: list[dict[str, Any]],
    stages: list[dict[str, Any]],
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None,
    review_one: Callable[[dict[str, Any]], Awaitable[tuple[CouncilOpinion, dict[str, Any]]]],
    *,
    minimum_participation: float,
    quorum: float,
) -> list[CouncilOpinion]:
    opinions: list[CouncilOpinion] = []
    for index, member in enumerate(members):
        opinion, stage = await review_one(member)
        opinions.append(opinion)
        stages.append(stage)
        await _notify_seat(on_seat, opinion)
        remaining = len(members) - len(opinions)
        locked = None
        if remaining:
            locked = votes_decide_outcome(
                opinions,
                remaining=remaining,
                minimum_participation=minimum_participation,
                quorum=quorum,
            )
        if locked:
            tail = await _skip_members(members[index + 1 :], "early_quorum", stages, on_seat)
            opinions.extend(tail)
            break
    return opinions


async def _collect_opinions(
    members: list[dict[str, Any]],
    *,
    review_material: str,
    workspace_id: str,
    registry: Any,
    council: dict[str, Any],
    speed: dict[str, Any],
    stages: list[dict[str, Any]],
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None,
    skip_reason: str | None = None,
) -> list[CouncilOpinion]:
    if skip_reason:
        return await _skip_members(members, skip_reason, stages, on_seat)

    async def _one(member: dict[str, Any]) -> tuple[CouncilOpinion, dict[str, Any]]:
        return await _review_one(
            member,
            review_material=review_material,
            workspace_id=workspace_id,
            registry=registry,
            council=council,
        )

    if not speed["early_quorum"]:
        return await _collect_parallel(members, stages, on_seat, _one)
    return await _collect_until_locked(
        members,
        stages,
        on_seat,
        _one,
        minimum_participation=float(council.get("minimum_participation", 0.66)),
        quorum=float(council.get("quorum", 0.66)),
    )


class CouncilConfigError(ValueError):
    """``portal_council_config`` is present and not a legal per-request override."""


_SPEED_BOOLS = ("early_quorum", "single_model", "progress", "decompose")
_SPEED_STRINGS = ("single_model_model", "decompose_model")
_OVERRIDE_TOP_LEVEL = frozenset((*_SPEED_BOOLS, *_SPEED_STRINGS, "synthesizer_model", "members"))
_MEMBER_FIELDS = frozenset({"model", "max_tokens", "reasoning_max_tokens", "think"})


def _reject_unknown_keys(keys: set[str], allowed: frozenset[str], where: str) -> None:
    extra = sorted(keys - allowed)
    if extra:
        raise CouncilConfigError(f"{where} has unknown keys: {', '.join(extra)}")


def _expect_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise CouncilConfigError(f"{where} must be a boolean")
    return value


def _expect_model_name(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CouncilConfigError(f"{where} must be a non-empty string")
    return value


def _expect_int(value: Any, where: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CouncilConfigError(f"{where} must be an integer >= {minimum}")
    return value


def _validate_member_patch(seat_id: str, patch: Any) -> dict[str, Any]:
    where = f"portal_council_config.members.{seat_id}"
    if not isinstance(patch, dict):
        raise CouncilConfigError(f"{where} must be an object")
    _reject_unknown_keys(set(patch), _MEMBER_FIELDS, where)
    if not patch:
        names = ", ".join(sorted(_MEMBER_FIELDS))
        raise CouncilConfigError(f"{where} must set at least one of {names}")
    cleaned: dict[str, Any] = {}
    if "model" in patch:
        cleaned["model"] = _expect_model_name(patch["model"], f"{where}.model")
    if "max_tokens" in patch:
        cleaned["max_tokens"] = _expect_int(patch["max_tokens"], f"{where}.max_tokens", 64)
    if "reasoning_max_tokens" in patch:
        cleaned["reasoning_max_tokens"] = _expect_int(
            patch["reasoning_max_tokens"], f"{where}.reasoning_max_tokens", 0
        )
    if "think" in patch:
        cleaned["think"] = _expect_bool(patch["think"], f"{where}.think")
    return cleaned


def _validate_council_override(raw: Any, seat_ids: set[str]) -> dict[str, Any]:
    """Check the request override. Unknown keys are an error, not a silent drop."""
    if not isinstance(raw, dict):
        raise CouncilConfigError("portal_council_config must be an object")
    _reject_unknown_keys(set(raw), _OVERRIDE_TOP_LEVEL, "portal_council_config")
    cleaned: dict[str, Any] = {}
    for key in _SPEED_BOOLS:
        if key in raw:
            cleaned[key] = _expect_bool(raw[key], f"portal_council_config.{key}")
    for key in (*_SPEED_STRINGS, "synthesizer_model"):
        if key in raw:
            cleaned[key] = _expect_model_name(raw[key], f"portal_council_config.{key}")
    if "members" not in raw:
        return cleaned
    members = raw["members"]
    if not isinstance(members, dict):
        raise CouncilConfigError("portal_council_config.members must be an object keyed by seat id")
    unknown_seats = sorted(set(members) - seat_ids)
    if unknown_seats:
        raise CouncilConfigError(
            "portal_council_config.members has unknown seat: " + ", ".join(unknown_seats)
        )
    cleaned["members"] = {
        str(seat_id): _validate_member_patch(str(seat_id), members[seat_id]) for seat_id in members
    }
    return cleaned


def _applied_view(
    council: dict[str, Any], member_override: dict[str, Any] | None
) -> dict[str, Any]:
    """Flat effective config, using the request's key names so an echo can match."""
    speed = _speed_flags(council)
    applied: dict[str, Any] = {
        "early_quorum": speed["early_quorum"],
        "single_model": speed["single_model"],
        "single_model_model": speed["resident_model"],
        "progress": speed["progress"],
        "decompose": speed["decompose"],
        "decompose_model": speed["decompose_model"],
        "synthesizer_model": str(council.get("synthesizer_model") or ""),
    }
    if member_override is not None:
        applied["members"] = member_override
    return applied


def prepare_council_request(council: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Merge ``portal_council_config`` over one request's council block.

    No key returns ``council`` unchanged. A legal override returns a deep copy
    and stashes the effective config on ``_applied_config`` for the result
    metadata. The chat handler is the only caller, and it already required the
    pipeline API key.

    Request keys: ``early_quorum``, ``single_model``, ``single_model_model``,
    ``progress``, ``decompose``, ``decompose_model``, ``synthesizer_model``,
    and ``members`` keyed by seat id (``model``, ``max_tokens``,
    ``reasoning_max_tokens``, ``think``). ``single_model_model`` is the
    resident model.
    """
    if "portal_council_config" not in body:
        return council
    seat_ids = {str(member.get("id", "")) for member in council.get("members") or []}
    override = _validate_council_override(body.get("portal_council_config"), seat_ids)
    merged = copy.deepcopy(council)
    speed = dict(merged.get("speed") or {})
    for key in _SPEED_BOOLS:
        if key in override:
            speed[key] = override[key]
    if "single_model_model" in override:
        speed["resident_model"] = override["single_model_model"]
    if "decompose_model" in override:
        speed["decompose_model"] = override["decompose_model"]
    merged["speed"] = speed
    if "synthesizer_model" in override:
        merged["synthesizer_model"] = override["synthesizer_model"]
    member_override = override.get("members")
    if member_override:
        by_id = {str(member.get("id", "")): member for member in merged.get("members") or []}
        for seat_id, patch in member_override.items():
            by_id[seat_id].update(patch)
    merged["_applied_config"] = _applied_view(merged, member_override)
    return merged


async def run_council_review(
    body: dict[str, Any],
    council: dict[str, Any],
    *,
    registry: Any,
    workspace_id: str,
    on_seat: Callable[[CouncilOpinion], Awaitable[None]] | None = None,
) -> CouncilCompletion:
    """Run isolated reviewers, aggregate in code, and synthesize one answer."""
    started = time.monotonic()
    # Set only on a per-request copy. Pop so it never leaks into a seat prompt.
    applied_config = council.pop("_applied_config", None)
    speed = _speed_flags(council)
    members = _seat_members(council, speed)
    review_material = _render_review_material(body.get("messages") or [])
    stages: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    seat_material = review_material
    minimum_participation = float(council.get("minimum_participation", 0.66))
    quorum = float(council.get("quorum", 0.66))

    escalated: list[dict[str, Any]] = []
    if speed["decompose"] and speed["decompose_model"]:
        seat_material, settled, escalated = await _run_decompose(
            speed=speed,
            review_material=review_material,
            workspace_id=workspace_id,
            registry=registry,
            stages=stages,
        )

    # Every claim settled: no big-model vote. A partial sheet still runs the
    # seats, on the unsettled claims only. A failed or fully-escalated sheet
    # reviews the original submission.
    fully_settled = bool(settled) and not escalated

    if fully_settled:
        opinions = await _collect_opinions(
            members,
            review_material=seat_material,
            workspace_id=workspace_id,
            registry=registry,
            council=council,
            speed=speed,
            stages=stages,
            on_seat=on_seat,
            skip_reason="decompose_settled",
        )
        aggregate = _decompose_aggregate(
            decision_from_settled([str(item.get("disposition") or "") for item in settled]),
            len(members),
            minimum_participation=minimum_participation,
            quorum=quorum,
            settled_count=len(settled),
        )
    else:
        opinions = await _collect_opinions(
            members,
            review_material=seat_material,
            workspace_id=workspace_id,
            registry=registry,
            council=council,
            speed=speed,
            stages=stages,
            on_seat=on_seat,
        )
        aggregate = aggregate_opinions(
            opinions,
            minimum_participation=minimum_participation,
            quorum=quorum,
        )
        if settled:
            aggregate = _merge_settled(aggregate, opinions, settled)

    content, synth = await _synthesize(
        council=council,
        aggregate=aggregate,
        opinions=opinions,
        review_material=review_material,
        workspace_id=workspace_id,
        registry=registry,
        settled=settled,
    )
    _remember(
        stages,
        _stage_timing(
            "synthesizer",
            "synthesizer",
            str(council.get("synthesizer_model") or ""),
            synth.data if synth.called else None,
            skipped=False,
            called=synth.called,
        ),
    )
    timings = {
        "wall_s": round(time.monotonic() - started, 6),
        "speed": _recorded_speed(speed, council),
        "stages": stages,
    }
    from portal.platform.inference.router.trace import note as trace_note  # noqa: PLC0415

    trace_note(portal_council_timings=timings)
    created = int(time.time())
    data = {
        "id": f"chatcmpl-p5-council-{created}",
        "object": "chat.completion",
        "created": created,
        "model": workspace_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "portal_council": {
            "aggregate": asdict(aggregate),
            "reviewers": [asdict(opinion) for opinion in opinions],
            "timings": timings,
        },
    }
    if applied_config is not None:
        data["portal_council"]["applied_config"] = applied_config
    return CouncilCompletion(
        data=data,
        backend_id=synth.backend_id,
        model=str(council.get("synthesizer_model", "council")),
    )


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _content_chunk(base: dict[str, Any], content: str) -> bytes:
    return _sse(
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content},
                    "finish_reason": None,
                }
            ],
        }
    )


async def stream_council_review(
    body: dict[str, Any],
    council: dict[str, Any],
    slot: Any,
    *,
    registry: Any,
    workspace_id: str,
) -> Any:
    """SSE wrapper that owns the request slot across the full council run."""
    created = int(time.time())
    completion_task: asyncio.Task[CouncilCompletion] | None = None
    base = {
        "id": f"chatcmpl-p5-council-{created}",
        "object": "chat.completion.chunk",
        "created": created,
        "model": workspace_id,
    }
    try:
        yield _sse(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": "_Council reviewers are working independently…_\n\n",
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
        if _speed_flags(council).get("progress"):
            queue: asyncio.Queue[CouncilOpinion] = asyncio.Queue()

            async def _on_seat(opinion: CouncilOpinion) -> None:
                await queue.put(opinion)

            completion_task = asyncio.create_task(
                run_council_review(
                    body,
                    council,
                    registry=registry,
                    workspace_id=workspace_id,
                    on_seat=_on_seat,
                )
            )
            while not (completion_task.done() and queue.empty()):
                try:
                    opinion = await asyncio.wait_for(queue.get(), timeout=_STREAM_HEARTBEAT_S)
                except TimeoutError:
                    if not completion_task.done():
                        yield b": portal-council keep-alive\n\n"
                    continue
                yield _content_chunk(base, _verdict_line(opinion))
            completion = completion_task.result()
        else:
            completion_task = asyncio.create_task(
                run_council_review(
                    body,
                    council,
                    registry=registry,
                    workspace_id=workspace_id,
                )
            )
            while not completion_task.done():
                done, _pending = await asyncio.wait(
                    {completion_task},
                    timeout=_STREAM_HEARTBEAT_S,
                )
                if not done:
                    # SSE comments are invisible to OpenAI-compatible clients but
                    # keep proxies and client read-idle timers alive while the
                    # independent reviewers and synthesis are still running.
                    yield b": portal-council keep-alive\n\n"
            completion = completion_task.result()
        content = completion.data["choices"][0]["message"]["content"]
        yield _content_chunk(base, content)
        stop_payload: dict[str, Any] = {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        council_meta = completion.data.get("portal_council")
        if council_meta is not None:
            stop_payload["portal_council"] = council_meta
        yield _sse(stop_payload)
        yield b"data: [DONE]\n\n"
    finally:
        if completion_task is not None and not completion_task.done():
            completion_task.cancel()
            with suppress(asyncio.CancelledError):
                await completion_task
        slot.release()
