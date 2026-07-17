"""Analyst/expert-confidence verdict axis + similarity carry.

DESIGN_SEC_BLUE_ORCHESTRATION_V1 §3.2, extended (V2 build) to carry the
"similar / variant / novel" result from unknown_defense.compute_similarity so
the emerging-threat case is representable, not coerced into a wrong exact
match.

SEPARATE from episode.CAPABILITY_VERDICTS (harness truth). episode.derive_verdict
is NOT touched. This axis is produced by the reasoning (Hunter) and expert
sections; the expert's is the conclusive one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ANALYST_VERDICTS = ["CONFIRMED", "ANOMALOUS_UNCLASSIFIED", "RULED_OUT", "UNRESOLVED"]
AnalystVerdict = Literal["CONFIRMED", "ANOMALOUS_UNCLASSIFIED", "RULED_OUT", "UNRESOLVED"]

# Reachable by a model section; UNRESOLVED is orchestrator-only (a budget failure).
ANALYST_REACHABLE = ("CONFIRMED", "ANOMALOUS_UNCLASSIFIED", "RULED_OUT")
ORCHESTRATOR_ONLY = ("UNRESOLVED",)

# Mirror of unknown_defense.MatchGrade values (kept as strings to avoid a hard
# import cycle; the reasoning section fills these from compute_similarity()).
MATCH_GRADES = ("EXACT", "SIMILAR", "NONE")


@dataclass
class SectionOutput:
    """Structured output of one reasoning/expert section turn.

    Exactly one of {verdict, request_more} is operative:
      - verdict in ANALYST_REACHABLE -> a conclusion (expert's is terminal)
      - request_more (non-empty) -> loop continues (design §3.1.a)
    Similarity carry (match_grade/similar_to) makes the emerging-threat case
    first-class: match_grade == "SIMILAR" with a named technique => a variant
    worth ANOMALOUS_UNCLASSIFIED + review, never a forced CONFIRMED (I8).
    """

    verdict: AnalystVerdict | None = None
    technique_ids: list[str] = field(default_factory=list)  # required iff CONFIRMED
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    request_more: str = ""
    match_grade: str = "NONE"  # EXACT | SIMILAR | NONE
    similar_to: list[str] = field(default_factory=list)  # nearest known technique(s) when SIMILAR
    section: str = ""  # "reasoning" | "expert" (provenance)
    raw: str = ""

    def is_conclusion(self) -> bool:
        return self.verdict in ANALYST_REACHABLE

    def wants_more(self) -> bool:
        return bool(self.request_more) and self.verdict is None


# Backwards-friendly alias (V1 called this AnalystOutput).
AnalystOutput = SectionOutput


def is_terminal(verdict: str | None) -> bool:
    return verdict in ANALYST_VERDICTS


def validate_output(out: SectionOutput) -> tuple[bool, str]:
    """Structural validity only. Grounding of CONFIRMED is enforced downstream
    by _cite_or_drop + telemetry grounding (Slice 4), not here."""
    if out.verdict is None and not out.wants_more():
        return False, "neither a verdict nor a request_more spec"
    if out.verdict is not None and out.verdict not in ANALYST_VERDICTS:
        return False, f"unknown verdict {out.verdict!r}"
    if out.match_grade not in MATCH_GRADES:
        return False, f"bad match_grade {out.match_grade!r}"
    if out.verdict == "CONFIRMED" and not out.technique_ids:
        return False, "CONFIRMED requires at least one technique_id"
    if out.verdict in ("CONFIRMED", "RULED_OUT") and not (out.evidence or out.reasoning):
        return False, f"{out.verdict} requires evidence or reasoning"
    if out.match_grade == "SIMILAR" and not out.similar_to:
        return False, "SIMILAR match_grade requires a named similar_to technique"
    return True, "ok"
