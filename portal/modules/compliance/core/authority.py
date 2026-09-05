"""Content-derived authority classification; filenames never confer force."""

from __future__ import annotations

import re

AUTHORITY_CLASSES = (
    "regulatory_requirement",
    "plan",
    "order",
    "approved_interpretation",
    "guidance",
    "rsaw",
    "technical_rationale",
    "commentary",
    "internal_commitment",
    "evidence",
    "unknown",
)


def classify(text: str, *, binding_effect: str = "unknown") -> str:
    lowered = text.lower()
    if binding_effect == "regulatory" and re.search(r"\bshall\b", lowered):
        return "regulatory_requirement"
    signals = (
        ("approved interpretation", "approved_interpretation"),
        ("implementation plan", "plan"),
        ("order no.", "order"),
        ("reliability standard audit worksheet", "rsaw"),
        ("technical rationale", "technical_rationale"),
        ("guidance", "guidance"),
        ("evidence", "evidence"),
    )
    for cue, result in signals:
        if cue in lowered:
            return result
    if binding_effect == "internally_mandatory" and re.search(r"\b(shall|must)\b", lowered):
        return "internal_commitment"
    return "unknown"


def may_create_obligation(authority_class: str) -> bool:
    return authority_class in {
        "regulatory_requirement",
        "order",
        "approved_interpretation",
        "internal_commitment",
    }
