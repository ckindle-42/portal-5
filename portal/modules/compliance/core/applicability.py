"""Applicability gate (T3 Phase 5). ``[GATE]`` — build the schema and the gating
logic, derive the dimensions from what the register actually uses, then stop.

**Asset scope is operator input.** Which BES Cyber Systems exist and at what
impact rating is not derivable from any document in the corpus. This module
presents the schema, the dimensions, and what each choice includes or excludes;
it does **not** populate a scope by inference, and a coverage matrix must not run
without one — an ungated matrix produces false gaps for requirements that do not
apply, and false gaps erode trust as fast as false coverage creates exposure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Dimensions derived from the register's `applicable_systems` column (Phase 1):
# impact ratings {High, Medium} appear on the extracted Parts; Low-Impact
# obligations live in CIP-003 Attachment 1 (the documented Phase 1 shortfall) so
# `low` is a declared dimension the register cannot yet gate on its own.
IMPACT_RATINGS = ("high", "medium", "low")
ASSOCIATED_TYPES = ("bcs", "eacms", "pacs", "pca")

# Qualifiers the register's Parts carry beyond the impact rating.
QUALIFIERS = {
    "erc": 'Medium Impact BES Cyber Systems "with External Routable Connectivity" '
    "— several Parts apply only when ERC is present.",
    "control_center": 'some Medium Impact Parts are scoped to "at Control Centers".',
}


@dataclass
class AssetScope:
    """The operator's declaration of what exists. Every field is operator input.

    ``impact_present`` — which impact ratings the entity has any BES Cyber
    System at. ``associated_present`` — which associated system types exist.
    ``has_erc`` / ``has_control_center`` — whether any in-scope Medium Impact
    system has External Routable Connectivity / is at a Control Center.
    """

    impact_present: set[str] = field(default_factory=set)  # subset of IMPACT_RATINGS
    associated_present: set[str] = field(default_factory=set)  # subset of ASSOCIATED_TYPES
    has_erc: bool = True
    has_control_center: bool = True
    declared_by: str = ""  # operator name — empty means undeclared
    declared_at: str = ""

    @property
    def is_declared(self) -> bool:
        return bool(self.declared_by and self.impact_present)


def parse_applicable_systems(text: str) -> dict:
    """Structured applicability of one register Part, from its verbatim
    `applicable_systems` cell."""
    t = text or ""
    low = t.lower()
    impacts = {r for r in IMPACT_RATINGS if re.search(rf"\b{r} impact\b", low)}
    assoc = set()
    if re.search(r"\bBES Cyber System", t):
        assoc.add("bcs")
    for a in ("eacms", "pacs"):
        if re.search(rf"\b{a.upper()}\b", t):
            assoc.add(a)
    if re.search(r"\bPCAs?\b", t):
        assoc.add("pca")
    return {
        "impacts": impacts or {"high", "medium"},  # a blank cell = the default CIP scope
        "associated": assoc or {"bcs"},
        "requires_erc": "external routable connectivity" in low,
        "at_control_center": "control center" in low,
        "verbatim": t,
    }


def applicable(part_applicable_systems: str, scope: AssetScope) -> tuple[bool, str]:
    """(applies, reason). Raises nothing — an undeclared scope is the caller's
    gate to check (``scope.is_declared``); here an undeclared scope is treated as
    'unknown', which is neither in nor out."""
    if not scope.is_declared:
        return False, "asset scope undeclared — gate not satisfied"
    a = parse_applicable_systems(part_applicable_systems)
    if a["impacts"].isdisjoint(scope.impact_present):
        return (
            False,
            f"Part scoped to {sorted(a['impacts'])}; entity has {sorted(scope.impact_present)}",
        )
    if (
        a["associated"]
        and a["associated"] != {"bcs"}
        and a["associated"].isdisjoint(scope.associated_present | {"bcs"})
    ):
        return False, f"Part scoped to associated {sorted(a['associated'])}; entity has none"
    if a["requires_erc"] and not scope.has_erc:
        return False, "Part requires External Routable Connectivity; entity declares none"
    if a["at_control_center"] and not scope.has_control_center:
        return False, "Part scoped to Control Centers; entity declares none"
    return True, "in scope"


def gate_presentation() -> dict:
    """``[GATE]`` 1 — the schema, the dimensions, and what each choice
    includes/excludes. Report; do not choose."""
    return {
        "gate": "asset applicability scope (T3 Phase 5)",
        "why_operator_input": "Which BES Cyber Systems exist and at what impact "
        "rating is not derivable from any document in the corpus.",
        "dimensions": {
            "impact_present": {
                "choices": list(IMPACT_RATINGS),
                "high": "includes every High Impact Part (CIP-004..011 core obligations).",
                "medium": "includes Medium Impact Parts; several are further gated by ERC.",
                "low": "CIP-003 Attachment 1 sections 1-5. The register does not yet "
                "carry these Parts (Phase 1 shortfall), so selecting `low` alone "
                "cannot be gated by the current register.",
            },
            "associated_present": {
                "choices": list(ASSOCIATED_TYPES),
                "excludes": "omitting e.g. `pacs` drops the ~9 Parts scoped only to PACS.",
            },
            "has_erc": "false excludes the Medium-Impact-with-ERC Parts "
            "(CIP-005 R1/R2, parts of CIP-007).",
            "has_control_center": "false excludes the Control-Center-scoped Parts "
            "(CIP-006 R1 physical, CIP-012).",
        },
        "consequence_of_skipping": "an ungated coverage matrix reports false gaps "
        "for every Part the entity is out of scope for.",
        "recommendation": "report to operator; do not infer.",
    }
