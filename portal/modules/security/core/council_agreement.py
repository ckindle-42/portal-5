"""Compatibility adapter from legacy security votes to Portal Council Review.

The retired security recall-council remains callable by historical benches and
the opt-in CLI mode, but it no longer owns quorum math.  Every participation and
vote threshold is delegated to the platform council primitive
``portal.platform.inference.router.council.aggregate_opinions``.  This module
only translates between the detection and review verdict domains:

* a member naming a candidate technique becomes SUPPORT for that candidate;
* another conclusive member becomes REJECT for that candidate;
* a non-concluding member becomes a non-participating ABSTAIN;
* a unanimous RULED_OUT roster becomes SUPPORT for the benign disposition.

The compatibility result retains the security pipeline's historical semantics:
  - techniques agreed by >= quorum of council members -> candidate CONFIRMED
    (still passes blue._cite_or_drop downstream — I2).
  - a shared signal the council cannot agree to map to one known technique ->
    ANOMALOUS_UNCLASSIFIED (disagreement-as-novelty — the emerging-threat case, I8).
  - council agrees there is nothing -> RULED_OUT.
  - no signal reached within budget -> UNRESOLVED (orchestrator, not here).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from portal.platform.inference.router.council import CouncilOpinion, aggregate_opinions

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


def _platform_opinions(
    members: list[SectionOutput],
    *,
    supports: Callable[[SectionOutput], bool],
) -> list[CouncilOpinion]:
    """Translate one binary detection-domain question onto the review contract."""
    opinions: list[CouncilOpinion] = []
    for index, member in enumerate(members):
        concluded = member.is_conclusion()
        opinions.append(
            CouncilOpinion(
                member_id=f"security-seat-{index + 1}",
                label=f"Security seat {index + 1}",
                model="legacy-security-council",
                recommendation=("SUPPORT" if supports(member) else "REJECT")
                if concluded
                else "ABSTAIN",
                confidence=1.0 if concluded else 0.0,
                valid=concluded,
                error="" if concluded else "member did not reach a conclusion",
            )
        )
    return opinions


def compute_agreement(
    members: list[SectionOutput],
    *,
    quorum: float = 0.5,
    min_participation: float = 0.67,
) -> AgreementResult:
    """Deterministic consensus over council members' section outputs.

    quorum is the member-fraction a technique must reach to be CONFIRMED-eligible.
    A shared-but-unagreed signal (members conclude *something* suspicious, but no
    technique reaches quorum) routes to ANOMALOUS_UNCLASSIFIED with the union of
    near-miss / SIMILAR neighbours — novelty from disagreement.
    """
    concluders = [m for m in members if m.is_conclusion()]
    participation = aggregate_opinions(
        _platform_opinions(members, supports=lambda _member: True),
        minimum_participation=min_participation,
        quorum=1.0,
    )
    roster = participation.roster
    if participation.participating == 0:
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

    candidate_techniques = sorted({t for member in concluders for t in member.technique_ids})
    technique_aggregates = {
        technique: aggregate_opinions(
            _platform_opinions(
                members,
                supports=lambda member, candidate=technique: candidate in set(member.technique_ids),
            ),
            minimum_participation=min_participation,
            quorum=quorum,
        )
        for technique in candidate_techniques
    }
    votes = {
        technique: aggregate.votes["SUPPORT"]
        for technique, aggregate in technique_aggregates.items()
    }
    similar_union = sorted({s for m in concluders for s in m.similar_to})

    # The platform aggregate is the implementation of record for both the
    # full-roster denominator and the minimum participation threshold.
    if participation.participating < participation.required_participation:
        observed_agreement = (
            round(max(votes.values()) / participation.roster, 3)
            if votes and participation.roster
            else 0.0
        )
        return AgreementResult(
            verdict="ANOMALOUS_UNCLASSIFIED",
            agreement=observed_agreement,
            dissent=dict(votes),
            needs_arbiter=True,
            similar_to=similar_union,
            rationale=(
                f"council participation {participation.participating}/{roster} below floor "
                f"{min_participation} — cross-check compromised, escalate"
            ),
        )

    if votes:
        top_votes = max(votes.values())
        frac = top_votes / roster
        agreed = sorted(
            technique
            for technique, aggregate in technique_aggregates.items()
            if aggregate.votes["SUPPORT"] >= aggregate.required_votes
        )
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

    # Ask the same platform primitive whether the full roster supports the
    # benign disposition.  quorum=1.0 intentionally preserves the old
    # unanimous-benign rule.
    benign = aggregate_opinions(
        _platform_opinions(members, supports=lambda member: member.verdict == "RULED_OUT"),
        minimum_participation=min_participation,
        quorum=1.0,
    )
    if benign.decision == "SUPPORT":
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
