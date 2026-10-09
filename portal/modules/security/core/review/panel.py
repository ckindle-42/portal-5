"""review.panel -- several judges, one deterministic decision.

Participation and quorum are computed by code over the FULL roster using the platform council
primitive (``aggregate_opinions``): a seat that errors or abstains never shrinks the roster, and
no outcome is reached by a minority. Mapping: ``something`` -> SUPPORT, ``nothing`` -> REJECT,
``unsure`` -> ABSTAIN (visible, non-voting); anything the council cannot decide (ESCALATE /
REVISE) is ``unsure``. Silencing a concern therefore needs a quorum of independent seats; it
never happens on one model's say-so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from portal.platform.inference.router.council import CouncilOpinion, aggregate_opinions

from .contracts import Claim, JudgeRecord, ReviewConcern, Verdict
from .intake import IntakeResult
from .judge import ModelClient, ToolBox, run_judge

_RECOMMENDATION = {
    Verdict.SOMETHING: "SUPPORT",
    Verdict.NOTHING: "REJECT",
    Verdict.UNSURE: "ABSTAIN",
}
_DECISION = {"SUPPORT": Verdict.SOMETHING, "REJECT": Verdict.NOTHING}


@dataclass(frozen=True)
class PanelPolicy:
    """Recorded in the stamp; chosen on the measurement plane, not assumed."""

    minimum_participation: float
    quorum: float


def panel_verdict(records: Sequence[JudgeRecord], policy: PanelPolicy) -> JudgeRecord:
    opinions = [
        CouncilOpinion(
            member_id=f"m{i}",
            label=r.model,
            model=r.model,
            recommendation=_RECOMMENDATION[r.verdict],
            confidence=r.confidence,
            valid=not r.degraded,
            error=r.degraded,
        )
        for i, r in enumerate(records)
    ]
    aggregate = aggregate_opinions(
        opinions, minimum_participation=policy.minimum_participation, quorum=policy.quorum
    )
    verdict = _DECISION.get(aggregate.decision, Verdict.UNSURE)

    claims: dict[str, Claim] = {}
    for record in records:
        if record.verdict == Verdict.SOMETHING:
            for claim in record.claims:
                claims.setdefault(claim.text, claim)
    voters = [r for r in records if not r.degraded and r.verdict != Verdict.UNSURE]
    panel: dict[str, Any] = {
        "decision": aggregate.decision,
        "votes": dict(aggregate.votes),
        "participation": aggregate.participation,
        "dissent": list(aggregate.dissent),
        "rationale": aggregate.rationale,
        "members": [{"model": r.model, "verdict": r.verdict.value} for r in records],
    }
    return JudgeRecord(
        model="panel:" + ",".join(r.model for r in records),
        verdict=verdict,
        confidence=sum(r.confidence for r in voters) / len(voters) if voters else 0.0,
        claims=tuple(claims.values()),
        dropped_claims=sum(r.dropped_claims for r in records),
        challenger_verdict=";".join(r.challenger_verdict for r in records),
        panel=panel,
        rounds=max((r.rounds for r in records), default=0),
        degraded="" if any(not r.degraded for r in records) else "every panel member failed",
        evidence_shown=max((r.evidence_shown for r in records), default=0),
        evidence_total=max((r.evidence_total for r in records), default=0),
    )


def run_panel(
    concern: ReviewConcern,
    window: IntakeResult,
    *,
    members: Sequence[tuple[ModelClient, str]],
    policy: PanelPolicy,
    tools: ToolBox | None = None,
    challenger_model: str | None = None,
    max_rounds: int = 3,
    max_events: int = 40,
    max_tokens: int = 2048,
) -> JudgeRecord:
    records = [
        run_judge(
            concern,
            window,
            client=client,
            model=model,
            tools=tools,
            challenger_model=challenger_model,
            max_rounds=max_rounds,
            max_events=max_events,
            max_tokens=max_tokens,
        )
        for client, model in members
    ]
    return panel_verdict(records, policy)
