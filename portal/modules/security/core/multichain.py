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
DECISIONS = ("AUTO_CONFIRM", "ESCALATE", "DISMISS")


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
    verdict: str  # CONFIRMED | ANOMALOUS_UNCLASSIFIED | RULED_OUT
    technique_ids: list[str] = field(default_factory=list)
    agreement: float = 0.0  # top technique's independent-chain-vote fraction
    dissent: dict = field(default_factory=dict)  # technique -> chain-vote count
    similar_to: list[str] = field(default_factory=list)
    evidence_diversity: int = 0  # distinct telemetry sourcetypes covered across chains
    escalation_reason: str = ""
    rationale: str = ""


def consolidate(chains: list[ChainResult], *, quorum: float = 0.5) -> ConsolidationResult:
    """Cool N independent chains into one operator decision.

    quorum is the fraction of *concluding* chains that must independently agree
    on a technique for AUTO_CONFIRM. A shared-but-unagreed signal (chains found
    something suspicious, but no technique reached quorum across independent
    investigations) is the strong ESCALATE case — exactly the "unknown read"
    the concept is built to surface, not bury.
    """
    concluders = [c for c in chains if c.is_conclusion()]
    diversity = len({s for c in chains for s in c.evidence_sources})

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
        )

    n = len(concluders)
    votes: Counter = Counter()
    for c in concluders:
        for t in set(c.technique_ids):
            votes[t] += 1
    similar_union = sorted({s for c in concluders for s in c.similar_to})

    if votes:
        top, top_votes = votes.most_common(1)[0]
        frac = top_votes / n
        agreed = sorted(t for t, v in votes.items() if v / n >= quorum)
        if agreed:
            return ConsolidationResult(
                decision="AUTO_CONFIRM",
                verdict="CONFIRMED",
                technique_ids=agreed,
                agreement=round(frac, 3),
                dissent=dict(votes),
                similar_to=similar_union,
                evidence_diversity=diversity,
                rationale=(
                    f"{len(agreed)} technique(s) independently confirmed by "
                    f">= quorum {quorum} of {n} chains"
                ),
            )
        # Signal exists across independent chains, but no technique reached
        # quorum — independent investigations diverged. The strong ESCALATE.
        return ConsolidationResult(
            decision="ESCALATE",
            verdict="ANOMALOUS_UNCLASSIFIED",
            agreement=round(frac, 3),
            dissent=dict(votes),
            similar_to=similar_union,
            evidence_diversity=diversity,
            escalation_reason=(
                "independent chains surfaced signal but diverged — no technique "
                f"reached quorum {quorum} (dissent: {dict(votes)})"
            ),
            rationale="divergent independent investigations — human review",
        )

    # No technique votes at all — chains concluded without naming a technique.
    benign = sum(c.verdict == "RULED_OUT" for c in concluders)
    if benign == n:
        return ConsolidationResult(
            decision="DISMISS",
            verdict="RULED_OUT",
            agreement=1.0,
            evidence_diversity=diversity,
            rationale="all independent chains ruled it out",
        )
    # Mixed benign / anomalous-without-technique — a shared unease with no
    # concrete claim. Escalate rather than silently dismiss.
    return ConsolidationResult(
        decision="ESCALATE",
        verdict="ANOMALOUS_UNCLASSIFIED",
        similar_to=similar_union,
        evidence_diversity=diversity,
        escalation_reason="chains split benign vs. anomalous with no concrete technique",
        rationale="unresolved unease across chains — human review",
    )


def to_section_output(res: ConsolidationResult) -> SectionOutput:
    """Fold the consolidation into the pipeline's standard SectionOutput so
    scoring / cite-or-drop / the OrchestrationResult trace treat it like any
    other section."""
    return SectionOutput(
        verdict=res.verdict,
        technique_ids=list(res.technique_ids),
        reasoning=res.rationale,
        match_grade="SIMILAR"
        if (res.verdict == "ANOMALOUS_UNCLASSIFIED" and res.similar_to)
        else "NONE",
        similar_to=list(res.similar_to),
        section="consolidation",
    )
