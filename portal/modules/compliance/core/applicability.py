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

# Dimensions derived from the register's `applicable_systems` column: impact
# ratings {High, Medium} appear on the extracted Parts, and the bright-line
# criteria that *define* High/Medium/Low now live in the register as CIP-002
# Attachment 1 nodes (TASK_CIP_REGISTER_COMPLETENESS_V1 §1.4). CIP-003
# Attachment 1's low-impact *plan sections* (1–5) are still not extracted, so a
# `low`-only entity's specific obligations remain out of register scope.
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
    """The entity's applicability facts.

    ``impact_present`` — which impact ratings the entity has any BES Cyber
    System at. ``associated_present`` — which associated system types exist.
    ``has_erc`` / ``has_control_center`` — whether any in-scope Medium Impact
    system has External Routable Connectivity / is at a Control Center;
    ``None`` means unconfirmed (P3 §8: unknown is a real state, not a
    default-True inclusion and not a default-False exclusion).

    ``is_confirmed`` distinguishes an OPERATOR's authenticated declaration
    (``declared_by`` is a real principal, e.g. from a confirmed review
    decision) from a corpus-derived CANDIDATE (``declared_by`` starts with
    ``"derived:"``) — a candidate keeps analysis provisional (``UNKNOWN``),
    never silently promoted to an approved ``APPLIES``/``DOES_NOT_APPLY``.
    ``conflicted`` marks contradictory unresolved candidate declarations.
    """

    impact_present: set[str] = field(default_factory=set)  # subset of IMPACT_RATINGS
    associated_present: set[str] = field(default_factory=set)  # subset of ASSOCIATED_TYPES
    has_erc: bool | None = True
    has_control_center: bool | None = True
    declared_by: str = ""  # operator/derivation name — empty means undeclared
    declared_at: str = ""
    conflicted: bool = False

    @property
    def is_declared(self) -> bool:
        return bool(self.declared_by and self.impact_present)

    @property
    def is_confirmed(self) -> bool:
        """True only for an authenticated operator declaration — never for a
        corpus-derived candidate (``declared_by`` prefixed ``"derived:"``)."""
        return self.is_declared and not self.declared_by.startswith("derived:")


def parse_applicable_systems(text: str) -> dict:
    """Structured applicability of one register Part, from its verbatim
    `applicable_systems` cell. ``impacts_unknown`` is True when the cell
    named no impact rating at all — the legacy ``impacts`` field still
    defaults such a blank cell to {"high","medium"} for ``applicable()``'s
    unchanged legacy behavior (see its docstring), but ``impacts_unknown``
    lets ``applicability_state`` report this honestly as UNKNOWN instead of
    silently inheriting that default (F07)."""
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
        "impacts_unknown": not impacts,
        "associated": assoc or {"bcs"},
        "requires_erc": "external routable connectivity" in low,
        "at_control_center": "control center" in low,
        "verbatim": t,
    }


APPLICABILITY_STATES = ("APPLIES", "DOES_NOT_APPLY", "UNKNOWN", "CONFLICTED")


def applicability_state(part_applicable_systems: str, scope: AssetScope) -> tuple[str, str]:
    """(state, reason) — four-state applicability (P3 §8 / F07): ``APPLIES``,
    ``DOES_NOT_APPLY``, ``UNKNOWN`` (scope undeclared, or the scope is a
    corpus-derived CANDIDATE never confirmed by the operator — see
    ``AssetScope.is_confirmed``), and ``CONFLICTED`` (the scope itself
    carries contradictory candidate declarations — see ``scope.conflicted``).
    An ``UNKNOWN`` Part stays in a provisional analysis's denominator; it is
    never silently excluded or treated as ``DOES_NOT_APPLY``."""
    if scope.conflicted:
        return "CONFLICTED", "asset scope has contradictory unresolved candidate declarations"
    if not scope.is_declared:
        return "UNKNOWN", "asset scope undeclared — gate not satisfied"
    if not scope.is_confirmed:
        return (
            "UNKNOWN",
            "asset scope is a corpus-derived CANDIDATE, not an operator-confirmed "
            "declaration — provisional analysis continues, but this is not APPLIES/DOES_NOT_APPLY",
        )
    a = parse_applicable_systems(part_applicable_systems)
    if a["impacts_unknown"]:
        return "UNKNOWN", "Part's applicable-systems text is blank/unparsed — impact rating unknown"
    shared_impact = a["impacts"] & scope.impact_present
    if not shared_impact:
        return (
            "DOES_NOT_APPLY",
            f"Part scoped to {sorted(a['impacts'])}; entity has {sorted(scope.impact_present)}",
        )
    if (
        a["associated"]
        and a["associated"] != {"bcs"}
        and a["associated"].isdisjoint(scope.associated_present | {"bcs"})
    ):
        return (
            "DOES_NOT_APPLY",
            f"Part scoped to associated {sorted(a['associated'])}; entity has none",
        )
    # ERC / Control-Center qualifiers gate the MEDIUM path only. An entity with
    # any High Impact system is in scope for a High+Medium part regardless.
    medium_only = shared_impact == {"medium"}
    if medium_only and a["requires_erc"] and scope.has_erc is None:
        return "UNKNOWN", "Part (Medium path) requires ERC; entity's ERC status is unconfirmed"
    if medium_only and a["requires_erc"] and not scope.has_erc:
        return (
            "DOES_NOT_APPLY",
            "Part (Medium path) requires External Routable Connectivity; entity declares none",
        )
    if medium_only and a["at_control_center"] and scope.has_control_center is None:
        return "UNKNOWN", "Part (Medium path) scoped to Control Centers; entity status unconfirmed"
    if medium_only and a["at_control_center"] and not scope.has_control_center:
        return (
            "DOES_NOT_APPLY",
            "Part (Medium path) scoped to Control Centers; entity declares none",
        )
    return "APPLIES", "in scope"


def applicable(part_applicable_systems: str, scope: AssetScope) -> tuple[bool, str]:
    """(applies, reason). Raises nothing — an undeclared scope is the caller's
    gate to check (``scope.is_declared``); here an undeclared scope is treated
    as 'unknown', which is neither in nor out.

    DELIBERATELY UNCHANGED from its pre-P3 behavior: this is the function
    ``coverage_matrix`` gates on today, and collapsing its live production
    path onto the new four-state ``applicability_state()`` (below) without a
    corresponding UNKNOWN-aware cell type in ``coverage.py`` would silently
    convert corpus-derived-but-unconfirmed scope into false NOT_APPLICABLE
    exclusions — trading one F07 shortcut for another. ``applicability_state``
    is additive new capability for P5/P7 to integrate deliberately; it is not
    wired into this gate yet."""
    if not scope.is_declared:
        return False, "asset scope undeclared — gate not satisfied"
    a = parse_applicable_systems(part_applicable_systems)
    shared_impact = a["impacts"] & scope.impact_present
    if not shared_impact:
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
    medium_only = shared_impact == {"medium"}
    # `is False` (not `not ...`): an unconfirmed `None` stays inclusive here,
    # matching this function's documented "absence of evidence never
    # excludes" contract — only an EXPLICIT False declaration excludes.
    if medium_only and a["requires_erc"] and scope.has_erc is False:
        return (
            False,
            "Part (Medium path) requires External Routable Connectivity; entity declares none",
        )
    if medium_only and a["at_control_center"] and scope.has_control_center is False:
        return False, "Part (Medium path) scoped to Control Centers; entity declares none"
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
                "low": "CIP-003 Attachment 1 sections 1-6 (Section 6 vendor "
                "electronic remote access is CIP-003-9). These are now in the "
                "register (TASK_CIP_REGISTER_COMPLETENESS_V1 §1.4 / P4), so a "
                "`low`-only entity gates on them directly.",
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
