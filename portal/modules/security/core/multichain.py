"""Multi-chain consolidation — the "cooling" / triage decision across several
INDEPENDENT investigative chains.

This is the piece the Council of Agreement (`council_agreement.py`) is not:
the council votes N interpreters over ONE shared evidence pool (one lead
investigator hunts, everyone else just concludes from the same context). A
real multi-model multi-chain analyst runs N *independent* chains — each forms
its own hypothesis, pulls its own evidence, hunts its own way — and then
consolidates across chains that saw DIFFERENT evidence. Agreement reached by
independent investigation is a far stronger signal than agreement forced by
identical input; divergence after independent investigation is a far stronger
"a human needs to look at this" signal.

The consolidation produces one of three OPERATOR DECISIONS (not just verdicts):
  - AUTO_CONFIRM  ("we've detected a known bad") — >= quorum of independent
    chains converged on the same known technique. Still passes blue's
    never-invent gate downstream (I2).
  - ESCALATE      ("we need a human to look at this") — the chains surfaced
    real signal but did NOT converge: a genuine unknown / disagreement across
    independent investigations (the emerging-threat case, I8). First-class
    outcome, never a fallback.
  - DISMISS       ("ruled out") — the chains independently found nothing.

Deterministic and auditable — code decides, like the rest of the harness's
truth plane (I1). No live calls; operates on already-gathered chain outputs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .analyst_verdict import SectionOutput

# Operator decisions — what the analyst tells the SOC to DO, distinct from the
# per-chain analyst verdicts (CONFIRMED / ANOMALOUS_UNCLASSIFIED / RULED_OUT).
# Known-bad detection and unknown-surfacing are SEPARATE channels a single run
# can produce at once (a real analyst can confirm one thing AND flag another) —
# CONFIRM_AND_ESCALATE is the both-at-once outcome, not a forced either/or.
DECISIONS = ("AUTO_CONFIRM", "CONFIRM_AND_ESCALATE", "ESCALATE", "DISMISS")


@dataclass
class ChainResult:
    """One independent investigative chain's outcome.

    Unlike a council member (which concludes from a shared pool), a chain
    carries `evidence_sources` — the telemetry sourcetypes IT chose to query
    while hunting its own hypothesis — so consolidation can measure how much
    of the telemetry surface the chains collectively covered (the coverage
    win that multi-chain exists for, and the direct structural answer to the
    single-lead HUNTER_MISS problem).
    """

    model: str
    verdict: str  # CONFIRMED | ANOMALOUS_UNCLASSIFIED | RULED_OUT | UNRESOLVED
    technique_ids: list[str] = field(default_factory=list)
    similar_to: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    # CONFIRMED claims this chain made that failed its citation gate —
    # quarantined audit data (2026-07-23). Deliberately excluded from quorum
    # votes AND from review leads: before this field existed, a demoted
    # fabrication rode along in technique_ids/similar_to and could vote a
    # hallucination toward AUTO_CONFIRM or earn it escalation credit.
    ungrounded_claims: list[str] = field(default_factory=list)

    def is_conclusion(self) -> bool:
        return self.verdict in ("CONFIRMED", "ANOMALOUS_UNCLASSIFIED", "RULED_OUT")

    def surfaced_signal(self) -> bool:
        """Did this chain find SOMETHING suspicious (a technique or a SIMILAR
        neighbour) — as opposed to concluding benign or never converging?"""
        return bool(self.technique_ids) or (
            self.verdict == "ANOMALOUS_UNCLASSIFIED" and bool(self.similar_to)
        )


@dataclass
class ConsolidationResult:
    decision: str  # one of DECISIONS
    verdict: str  # CONFIRMED | ANOMALOUS_UNCLASSIFIED | RULED_OUT (top-line, for scoring)
    # ── Two SEPARATE channels (known-bad detection vs. unknown-surfacing) ──
    # a single run can populate BOTH: confirm one thing AND flag another.
    confirmed_techniques: list[str] = field(default_factory=list)  # known-bad, auto-confirm channel
    review_leads: list[str] = field(default_factory=list)  # unknown/near-miss, escalate channel
    # ── Audit detail ──
    technique_ids: list[str] = field(
        default_factory=list
    )  # == confirmed_techniques (compat/scoring)
    agreement: float = 0.0  # top technique's independent-chain-vote fraction
    dissent: dict = field(default_factory=dict)  # technique -> chain-vote count
    similar_to: list[str] = field(default_factory=list)  # == review_leads (compat)
    evidence_diversity: int = 0  # distinct telemetry sourcetypes covered across chains
    escalation_reason: str = ""
    rationale: str = ""
    ungrounded_claims: list[str] = field(default_factory=list)  # union across chains — audit only


def _triage_decision(confirmed: list[str], review: list[str], *, any_conclusion: bool) -> str:
    """The "cooling" step: given the separated known-bad and unknown channels,
    route to the operator decision. Known-bad and unknown are not mutually
    exclusive — a run can do both, so CONFIRM_AND_ESCALATE is a real outcome,
    not a forced pick."""
    if confirmed and review:
        return "CONFIRM_AND_ESCALATE"
    if confirmed:
        return "AUTO_CONFIRM"
    if review or not any_conclusion:
        return "ESCALATE"
    return "DISMISS"


def consolidate(chains: list[ChainResult], *, quorum: float = 0.5) -> ConsolidationResult:
    """Cool N independent chains into one operator decision, keeping the
    KNOWN-BAD and UNKNOWN channels separate so a run can surface both.

    quorum is the fraction of *concluding* chains that must independently agree
    on a technique for it to land in the confirmed (known-bad) channel. Every
    other surfaced signal — a technique that got votes but missed quorum, or a
    SIMILAR near-miss neighbour from an anomalous chain — is a review lead in
    the unknown channel (the "someone needs to look at this" read, I8), never
    dropped just because a *different* technique happened to auto-confirm.
    """
    concluders = [c for c in chains if c.is_conclusion()]
    diversity = len({s for c in chains for s in c.evidence_sources})
    # Demoted (gate-failed) claims are carried for audit only — they never
    # vote, never become review leads (2026-07-23 design review).
    ungrounded_union = sorted({u for c in chains for u in c.ungrounded_claims})

    if not concluders:
        # Every chain ran out of budget / never converged — the orchestrator
        # gave up, not a benign finding. Escalate: a live analyst can't be
        # told "all clear" when the investigation never actually completed.
        return ConsolidationResult(
            decision="ESCALATE",
            verdict="ANOMALOUS_UNCLASSIFIED",
            evidence_diversity=diversity,
            escalation_reason="no chain reached a conclusion within budget",
            rationale="inconclusive — investigation did not complete",
            ungrounded_claims=ungrounded_union,
        )

    n = len(concluders)
    votes: Counter = Counter()
    for c in concluders:
        for t in set(c.technique_ids):
            votes[t] += 1
    similar_union = {s for c in concluders for s in c.similar_to}

    # KNOWN-BAD channel: techniques >= quorum of independent chains confirmed.
    confirmed = sorted(t for t, v in votes.items() if v / n >= quorum)
    # UNKNOWN channel: techniques that got real votes but missed quorum
    # (divergent independent investigations) + SIMILAR near-miss neighbours,
    # minus anything already auto-confirmed.
    below_quorum = {t for t, v in votes.items() if v / n < quorum}
    review = sorted((below_quorum | similar_union) - set(confirmed))

    # An ANOMALOUS chain that named neither a technique nor a SIMILAR neighbour
    # is still unease — a signal a human should see, even with nothing concrete
    # to hand them. It must escalate, never dismiss.
    has_unnamed_anomaly = any(
        c.verdict == "ANOMALOUS_UNCLASSIFIED" and not c.technique_ids and not c.similar_to
        for c in concluders
    )
    any_signal = bool(votes) or bool(similar_union) or has_unnamed_anomaly
    benign = sum(c.verdict == "RULED_OUT" for c in concluders)
    if not any_signal and benign == n:
        return ConsolidationResult(
            decision="DISMISS",
            verdict="RULED_OUT",
            agreement=1.0,
            evidence_diversity=diversity,
            rationale="all independent chains ruled it out",
            ungrounded_claims=ungrounded_union,
        )

    # Unnamed anomaly forces an escalation channel even with no concrete lead.
    decision = _triage_decision(
        confirmed, review, any_conclusion=not (has_unnamed_anomaly and not review and not confirmed)
    )
    if has_unnamed_anomaly and decision == "AUTO_CONFIRM":
        decision = "CONFIRM_AND_ESCALATE"
    top_frac = (votes.most_common(1)[0][1] / n) if votes else 0.0

    # Top-line verdict for downstream scoring: CONFIRMED if a known-bad landed
    # (even alongside review leads — the confirm is real), else ANOMALOUS.
    verdict = "CONFIRMED" if confirmed else "ANOMALOUS_UNCLASSIFIED"

    escalation_reason = ""
    if review:
        escalation_reason = (
            f"{len(review)} lead(s) need human review: {review} (dissent tally: {dict(votes)})"
        )
    elif has_unnamed_anomaly:
        escalation_reason = (
            "a chain flagged an anomaly it could not map to a known technique — "
            "unnamed unease, human review"
        )
    rationale_parts = []
    if confirmed:
        rationale_parts.append(
            f"{len(confirmed)} technique(s) independently confirmed by >= quorum {quorum} of {n} chains"
        )
    if review:
        rationale_parts.append(f"{len(review)} unresolved lead(s) escalated for review")
    rationale = "; ".join(rationale_parts) or "signal surfaced across chains"

    return ConsolidationResult(
        decision=decision,
        verdict=verdict,
        confirmed_techniques=confirmed,
        review_leads=review,
        technique_ids=confirmed,
        agreement=round(top_frac, 3),
        dissent=dict(votes),
        similar_to=sorted(similar_union),
        evidence_diversity=diversity,
        escalation_reason=escalation_reason,
        rationale=rationale,
        ungrounded_claims=ungrounded_union,
    )


def to_section_output(res: ConsolidationResult) -> SectionOutput:
    """Fold the consolidation into the pipeline's standard SectionOutput so
    scoring / cite-or-drop / the OrchestrationResult trace treat it like any
    other section.

    Both channels are carried forward: `technique_ids` = confirmed known-bad,
    `similar_to` = review leads. `match_grade` is SIMILAR whenever there are
    review leads (even alongside a confirm) so a CONFIRM_AND_ESCALATE run still
    surfaces its unknown channel downstream, never silently dropping it."""
    return SectionOutput(
        verdict=res.verdict,
        technique_ids=list(res.confirmed_techniques),
        reasoning=res.rationale,
        match_grade="SIMILAR" if res.review_leads else "NONE",
        similar_to=list(res.review_leads),
        section="consolidation",
        ungrounded_claims=list(res.ungrounded_claims),
    )
