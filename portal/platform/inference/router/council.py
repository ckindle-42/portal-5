"""Evidence-backed, isolated multi-model review for Council workspaces.

Council Review is deliberately separate from the sequential ``chain`` path:
reviewers receive the same review material but never see one another's output.
They return a small JSON contract, code computes participation/quorum over the
full roster, and only then may a synthesizer explain the deterministic result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None

_RECOMMENDATIONS = frozenset({"SUPPORT", "REVISE", "REJECT", "ABSTAIN"})
_DECISIONS = frozenset({"SUPPORT", "REVISE", "REJECT", "ESCALATE"})

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

Rules:
- Work independently. You cannot see other reviewers' answers.
- Use only the supplied review material. Do not invent repository state, test
  results, citations, requirements, or user constraints.
- Every substantive finding must identify its evidence.
- Use ABSTAIN when the material is insufficient for your assigned review.
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

    @property
    def participated(self) -> bool:
        """A valid ABSTAIN remains visible but does not cast a decision vote."""
        return self.valid and self.recommendation != "ABSTAIN"


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


def _message_text(data: dict[str, Any]) -> str:
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    return reasoning if isinstance(reasoning, str) else ""


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


async def _call_reviewer(
    member: dict[str, Any],
    *,
    review_material: str,
    workspace_id: str,
    registry: Any,
    max_tokens: int,
) -> CouncilOpinion:
    if _http_client is None:
        return parse_opinion(member, "", error="pipeline HTTP client is not initialized")

    model = str(member.get("model", ""))
    backend = _backend_for_model(registry, workspace_id, model)
    if backend is None:
        return parse_opinion(member, "", error=f"configured model is unavailable: {model}")

    system = f"{member.get('system', '')}\n\n{_REVIEW_CONTRACT}".strip()
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"## REVIEW MATERIAL\n\n{review_material}"},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    try:
        response = await _http_client.post(backend.chat_url, json=payload)
        response.raise_for_status()
        text = _message_text(response.json())
        return parse_opinion(member, text)
    except Exception as exc:
        logger.warning(
            "Council reviewer failed: workspace=%s member=%s model=%s error=%s",
            workspace_id,
            member.get("id"),
            model,
            type(exc).__name__,
        )
        return parse_opinion(member, "", error=f"{type(exc).__name__}: {exc}")


def _fallback_markdown(
    aggregate: CouncilAggregate,
    opinions: list[CouncilOpinion],
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
) -> tuple[str, str]:
    model = str(council.get("synthesizer_model", ""))
    backend = _backend_for_model(registry, workspace_id, model)
    if _http_client is None or backend is None:
        return _fallback_markdown(aggregate, opinions), backend.id if backend else "council"

    records = [asdict(opinion) for opinion in opinions]
    synthesis_packet = {
        "code_determined_decision": asdict(aggregate),
        "reviewers": records,
    }
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYNTHESIS_CONTRACT},
            {
                "role": "user",
                "content": (
                    f"## ORIGINAL REVIEW MATERIAL\n\n{review_material}\n\n"
                    "## VALIDATED COUNCIL PACKET\n\n"
                    f"{json.dumps(synthesis_packet, ensure_ascii=False)}"
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": int(council.get("synthesizer_max_tokens", 4096)),
    }
    try:
        response = await _http_client.post(backend.chat_url, json=payload)
        response.raise_for_status()
        text = _message_text(response.json()).strip()
        if text:
            # The machine decision is always rendered first, even if a weak
            # synthesizer later writes contradictory prose.
            prefix = (
                f"**Code-determined decision: {aggregate.decision}**  \n"
                f"Participation: {aggregate.participating}/{aggregate.roster}; "
                f"votes: {aggregate.votes}.\n\n"
            )
            return prefix + text, backend.id
    except Exception as exc:
        logger.warning(
            "Council synthesis failed: workspace=%s model=%s error=%s",
            workspace_id,
            model,
            type(exc).__name__,
        )
    return _fallback_markdown(aggregate, opinions), backend.id


async def run_council_review(
    body: dict[str, Any],
    council: dict[str, Any],
    *,
    registry: Any,
    workspace_id: str,
) -> CouncilCompletion:
    """Run isolated reviewers, aggregate in code, and synthesize one answer."""
    members = [dict(member) for member in council.get("members") or []]
    review_material = _render_review_material(body.get("messages") or [])
    opinions = list(
        await asyncio.gather(
            *[
                _call_reviewer(
                    member,
                    review_material=review_material,
                    workspace_id=workspace_id,
                    registry=registry,
                    max_tokens=int(council.get("reviewer_max_tokens", 4096)),
                )
                for member in members
            ]
        )
    )
    aggregate = aggregate_opinions(
        opinions,
        minimum_participation=float(council.get("minimum_participation", 0.66)),
        quorum=float(council.get("quorum", 0.66)),
    )
    content, backend_id = await _synthesize(
        council=council,
        aggregate=aggregate,
        opinions=opinions,
        review_material=review_material,
        workspace_id=workspace_id,
        registry=registry,
    )
    model = str(council.get("synthesizer_model", "council"))
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
        },
    }
    return CouncilCompletion(data=data, backend_id=backend_id, model=model)


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


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
        completion = await run_council_review(
            body,
            council,
            registry=registry,
            workspace_id=workspace_id,
        )
        content = completion.data["choices"][0]["message"]["content"]
        yield _sse(
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
        yield _sse(
            {
                **base,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        yield b"data: [DONE]\n\n"
    finally:
        slot.release()
