"""bully.relation_investigation -- relation-driven investigation
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 J.1, the interlock).

The RELATING stage's `Relation` (A.2/A.3) becomes the investigation arm's
starting point: "this resembles X -- confirm or refute" instead of a blank
prompt, and every uncertainty reason becomes an explicit investigation
question. Pure compute (COLD): this module only shapes the brief the
investigation arm consumes, it never calls a model itself (that stays in
`investigation.run_arm`, MASTER SS3 boundary).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_REASON_QUESTION_MAP: dict[str, str] = {
    "opaque_entities": "can entity identity be resolved for this source to sharpen the match?",
    "no_entity_identity": "is there a correlated source that carries entity identity here?",
    "discriminator_veto": "which discriminator contradicted the nearest match, and is it reliable?",
    "confidence_below_classification_floor": (
        "gather more evidence before trusting this relation's verdict"
    ),
    "novel_behavior": "characterize this novel behavior as a new anchor candidate",
}


def _question_for_reason(reason: str) -> str:
    prefix = reason.split(":", 1)[0]
    if prefix in _REASON_QUESTION_MAP:
        return _REASON_QUESTION_MAP[prefix]
    if prefix == "missing_dimension":
        dimension = reason.split(":", 1)[1] if ":" in reason else "unknown"
        return f"can {dimension} evidence be obtained for this neighbourhood?"
    if prefix == "thin_anchor_coverage":
        return "only a few anchors were considered -- are there more anchors for this family?"
    return f"investigate: {reason}"


def _base_question(relation: Any) -> str:
    # `nearest_knowns`/`verdict` is the provoked-grader (`relation.Relation`)
    # shape; `ranked_cousins`/`status` is the observed cousin grader
    # (`cousin_relation.CousinRelation`, TASK_BULLY_COUSIN_RELATION_V1 C.2) --
    # same (anchor_id, distance) shape under a different name, so this brief
    # works unmodified against either RELATING output.
    ranked = getattr(relation, "nearest_knowns", None)
    if ranked is None:
        ranked = getattr(relation, "ranked_cousins", ())
    verdict = getattr(relation, "verdict", None)
    if verdict is None:
        verdict = getattr(relation, "status", "")
    nearest = ranked[0][0] if ranked else None
    if nearest:
        return f"this resembles {nearest} ({verdict}) -- confirm or refute"
    return f"no anchor resembles this neighbourhood ({verdict}) -- characterize it"


@dataclass(frozen=True)
class InvestigationBrief:
    base_question: str
    questions: tuple[str, ...]
    relation: Any = field(repr=False)

    @property
    def uncertainty_question_count(self) -> int:
        return len(self.questions) - 1  # excludes the base question


def build_investigation_brief(relation: Any) -> InvestigationBrief:
    """One question per uncertainty reason, plus the base
    resembles-X-confirm-or-refute question first. Never fewer questions
    than uncertainty reasons -- a low-confidence relation (more reasons)
    always produces more investigation, not less."""
    questions = (
        _base_question(relation),
        *(_question_for_reason(r) for r in relation.uncertainty_reasons),
    )
    return InvestigationBrief(base_question=questions[0], questions=questions, relation=relation)


def investigate_from_relation(scope: Any, relation: Any) -> InvestigationBrief:
    """Default `observed_mode.run_observed(investigate_fn=...)` hook (J.1):
    shapes the brief only -- wiring an actual model-backed arm (e.g.
    `investigation.run_arm`) over this brief's questions is the caller's
    concern, kept out of this pure module (MASTER SS3)."""
    return build_investigation_brief(relation)
