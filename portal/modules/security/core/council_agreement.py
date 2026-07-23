"""Council of Agreement — cross-check multiple section outputs into one verdict.

Deterministic consensus backbone (auditable, code-decided like the rest of the
harness's truth) + an optional fed-expert arbiter for the hard disagreement
cases. Design intent (BUILD_PROGRAM V2 Appendix C; TASK gated-ablation Part II-A):
  - techniques agreed by >= quorum of council members -> candidate CONFIRMED
    (still passes blue._cite_or_drop downstream — I2).
  - a shared signal the council cannot agree to map to one known technique ->
    ANOMALOUS_UNCLASSIFIED (disagreement-as-novelty — the emerging-threat case, I8).
  - council agrees there is nothing -> RULED_OUT.
  - no signal reached within budget -> UNRESOLVED (orchestrator, not here).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analyst_verdict import SectionOutput


@dataclass
class AgreementResult:
    verdict: str  # CONFIRMED | ANOMALOUS_UNCLASSIFIED | RULED_OUT
    technique_ids: list[str] = field(default_factory=list)
    agreement: float = 0.0  # top technique's member-vote fraction
    dissent: dict = field(default_factory=dict)  # technique -> vote count (for audit)
    needs_arbiter: bool = False
    similar_to: list[str] = field(default_factory=list)
    rationale: str = ""


def compute_agreement(members: list[SectionOutput], *, quorum: float = 0.5) -> AgreementResult:
    """Deterministic consensus over council members' section outputs.

    quorum is the member-fraction a technique must reach to be CONFIRMED-eligible.
    A shared-but-unagreed signal (members conclude *something* suspicious, but no
    technique reaches quorum) routes to ANOMALOUS_UNCLASSIFIED with the union of
    near-miss / SIMILAR neighbours — novelty from disagreement.
    """
    concluders = [m for m in members if m.is_conclusion()]
    if not concluders:
        # Budget/convergence failure, NOT a benign finding (2026-07-23 design
        # review): this previously returned RULED_OUT — telling the SOC "all
        # clear" because no council member managed to conclude, the exact
        # failure multichain.consolidate's no-concluder branch escalates.
        # Mirror it: an incomplete investigation escalates, never dismisses.
        # needs_arbiter=True so a configured arbiter still gets its shot at a
        # real conclusion before the escalation stands.
        return AgreementResult(
            verdict="ANOMALOUS_UNCLASSIFIED",
            agreement=0.0,
            needs_arbiter=True,
            rationale="no member reached a conclusion — investigation incomplete, escalate",
        )

    n = len(concluders)
    votes: Counter = Counter()
    for m in concluders:
        for t in set(m.technique_ids):
            votes[t] += 1
    similar_union = sorted({s for m in concluders for s in m.similar_to})

    if votes:
        top, top_votes = votes.most_common(1)[0]
        frac = top_votes / n
        agreed = sorted(t for t, v in votes.items() if v / n >= quorum)
        if agreed:
            return AgreementResult(
                verdict="CONFIRMED",
                technique_ids=agreed,
                agreement=round(frac, 3),
                dissent=dict(votes),
                similar_to=similar_union,
                rationale=f"{len(agreed)} technique(s) at/above quorum {quorum}",
            )
        # signal exists but nobody reaches quorum -> disagreement-as-novelty
        return AgreementResult(
            verdict="ANOMALOUS_UNCLASSIFIED",
            agreement=round(frac, 3),
            dissent=dict(votes),
            similar_to=similar_union,
            needs_arbiter=True,
            rationale="council split — shared signal, no technique at quorum",
        )

    # all concluders were benign
    benign = sum(m.verdict == "RULED_OUT" for m in concluders)
    if benign == n:
        return AgreementResult(verdict="RULED_OUT", agreement=1.0, rationale="unanimous benign")
    return AgreementResult(
        verdict="ANOMALOUS_UNCLASSIFIED",
        needs_arbiter=True,
        similar_to=similar_union,
        rationale="mixed benign/anomalous without technique votes",
    )


def to_section_output(res: AgreementResult) -> SectionOutput:
    """Fold the agreement into the pipeline's standard SectionOutput (so scoring,
    cite-or-drop, and the OrchestrationResult trace treat it like any other)."""
    return SectionOutput(
        verdict=res.verdict,
        technique_ids=list(res.technique_ids),
        reasoning=res.rationale,
        match_grade="SIMILAR"
        if (res.verdict == "ANOMALOUS_UNCLASSIFIED" and res.similar_to)
        else "NONE",
        similar_to=list(res.similar_to),
        section="agreement",
    )
