"""Authority tiers and ``COMPLIANCE_CONFLICT`` (T3 Phase 3).

A **code-level rule with its own test**, not a prompt instruction — the persona
already carries prompt instructions and nothing verifies them.

Tier 0 standard · Tier 1 implementation plans, RSAWs, compliance guidance, FERC
orders · Tier 2 policy · Tier 3 procedure · Tier 4 evidence.

Every retrieved span carries its tier. When spans from **different** tiers make
conflicting normative or quantitative claims about the same obligation — *the
standard says 15 calendar months, the procedure says 18* — a
``COMPLIANCE_CONFLICT`` is emitted with both spans, both tiers, both citations.
It is **never reconciled, never averaged, and a lower tier never wins.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TIER_NAMES = {
    0: "standard",
    1: "implementation_plan_rsaw_guidance_ferc_order",
    2: "policy",
    3: "procedure",
    4: "evidence",
}

# document class -> tier. The retrieval layer tags each span's document with one
# of these classes; anything unrecognised is treated as the *lowest* authority
# (Tier 4) so it can never silently override a standard.
_DOC_CLASS_TIER = {
    "standard": 0,
    "nerc_standard": 0,
    "implementation_plan": 1,
    "rsaw": 1,
    "compliance_guidance": 1,
    "ferc_order": 1,
    "policy": 2,
    "procedure": 3,
    "work_instruction": 3,
    "evidence": 4,
    "audit_evidence": 4,
    "record": 4,
}


def classify_tier(doc_class: str) -> int:
    return _DOC_CLASS_TIER.get((doc_class or "").strip().lower(), 4)


@dataclass
class Span:
    text: str
    tier: int
    citation: str  # "CIP-007-6 R2 Part 2.2" | "OT-POL-014 §4.3 p12"
    doc_class: str = ""


# quantitative claim: a number + a compliance-relevant unit, optionally with a
# qualifier ("calendar", "business", "consecutive")
_QUANT_RE = re.compile(
    r"(?<![\w.])(\d{1,4})\s+(?:(calendar|business|consecutive)\s+)?"
    r"(day|days|month|months|year|years|hour|hours|week|weeks)\b",
    re.I,
)
# normative modal — a deontic conflict (a *shall* against a *should*/silence)
_MODAL_RE = re.compile(r"\b(shall|must|will|should|may|strive to|endeavor to)\b", re.I)


def _quant_claims(text: str) -> list[tuple[int, str, str | None, str]]:
    """[(value, unit, qualifier, verbatim)] for every numeric-duration claim.

    F05: values are NOT converted to a common day count. "1 calendar month",
    "30 calendar days" and "30 business days" are three different quantities
    wearing similar-looking numbers, not the same duration — a calendar month
    is not exactly 30 days, and a business-day count is not a calendar-day
    count. Only claims sharing the same ``(unit, qualifier)`` are numerically
    comparable; anything else is a comparison uncertainty (see
    ``detect_conflicts``), never a silent equivalence or a false conflict."""
    out = []
    for m in _QUANT_RE.finditer(text):
        n = int(m.group(1))
        qualifier = (m.group(2) or "").lower() or None
        unit = m.group(3).lower().rstrip("s")
        out.append((n, unit, qualifier, m.group(0)))
    return out


_RESOLUTION_TEXT = {
    "quantitative": (
        "NOT reconciled — the higher-tier claim governs the regulatory/policy "
        "floor. A stricter lower-tier commitment may be an intentional internal "
        "choice, not an error; SME review determines intentionality "
        "(TASK_COMPLIANCE_REASONING_V2 §7.2) rather than this rule."
    ),
    "deontic": (
        "NOT reconciled — the higher-tier obligation is mandatory regardless of "
        "how the lower-tier document phrases it; the lower-tier document should "
        "be reviewed to confirm it does not weaken a mandatory obligation."
    ),
    "same_tier_disagreement": (
        "NOT reconciled — two same-tier documents disagree about the same "
        "obligation; tier alone cannot decide which governs. SME review required "
        "to determine which is correct, or whether both are independently valid "
        "for different populations."
    ),
    "comparison_uncertainty": (
        "Abstained — the compared claims use different units/qualifiers with no "
        "reviewed conversion rule (a calendar month is not a fixed day count; a "
        "business-day count is not a calendar-day count). Neither equality nor "
        "conflict is asserted."
    ),
}


@dataclass
class ComplianceConflict:
    kind: str  # "quantitative" | "deontic" | "same_tier_disagreement" | "comparison_uncertainty"
    obligation: str  # a short label for what the spans disagree about
    higher: Span
    lower: Span
    detail: str
    same_tier: bool = False

    def to_dict(self) -> dict:
        return {
            "signal": "COMPLIANCE_CONFLICT"
            if self.kind != "comparison_uncertainty"
            else "COMPARISON_UNCERTAINTY",
            "kind": self.kind,
            "obligation": self.obligation,
            "detail": self.detail,
            "same_tier": self.same_tier,
            ("span_a" if self.same_tier else "higher_authority"): {
                "tier": self.higher.tier,
                "tier_name": TIER_NAMES.get(self.higher.tier, "?"),
                "citation": self.higher.citation,
                "text": self.higher.text,
            },
            ("span_b" if self.same_tier else "lower_authority"): {
                "tier": self.lower.tier,
                "tier_name": TIER_NAMES.get(self.lower.tier, "?"),
                "citation": self.lower.citation,
                "text": self.lower.text,
            },
            "resolution": _RESOLUTION_TEXT[self.kind],
        }


def detect_conflicts(spans: list[Span], obligation: str = "") -> list[ComplianceConflict]:
    """Pairwise across every pair of spans, including same tier (F05: "Support
    same-tier disagreement detection, scoped to equivalent obligations" — the
    caller is expected to have already scoped ``spans`` to one obligation, e.g.
    coverage.py's topic-overlap filter). Same-tier disagreement is reported as
    its own kind, never silently skipped and never as a cross-tier authority
    ruling."""
    conflicts: list[ComplianceConflict] = []
    for i, a in enumerate(spans):
        for b in spans[i + 1 :]:
            same_tier = a.tier == b.tier
            hi, lo = (a, b) if a.tier <= b.tier else (b, a)

            qa = _quant_claims(hi.text)
            qb = _quant_claims(lo.text)
            if qa and qb:
                # Only "business" genuinely changes the count (a business-day
                # calendar skips weekends/holidays); an unstated qualifier is
                # the ordinary calendar reading, same as an explicit
                # "calendar" — "18 months" and "15 calendar months" are the
                # same kind of quantity and ARE comparable. Different UNITS
                # (day vs month vs year) remain never converted (F05).
                keyed_a = {
                    (unit, "business" if qual == "business" else "calendar"): value
                    for value, unit, qual, _ in qa
                }
                keyed_b = {
                    (unit, "business" if qual == "business" else "calendar"): value
                    for value, unit, qual, _ in qb
                }
                shared = keyed_a.keys() & keyed_b.keys()
                disagreeing = {k for k in shared if keyed_a[k] != keyed_b[k]}
                if disagreeing:
                    ta = ", ".join(t for _, _, _, t in qa)
                    tb = ", ".join(t for _, _, _, t in qb)
                    conflicts.append(
                        ComplianceConflict(
                            kind="same_tier_disagreement" if same_tier else "quantitative",
                            obligation=obligation or "duration",
                            higher=hi,
                            lower=lo,
                            detail=f"{hi.citation} says [{ta}]; {lo.citation} says [{tb}]",
                            same_tier=same_tier,
                        )
                    )
                    continue
                if not shared:
                    # different (unit, qualifier) pairs on each side — no
                    # reviewed conversion rule exists (F05). Abstain rather
                    # than silently treat them as equal or as a conflict.
                    ta = ", ".join(t for _, _, _, t in qa)
                    tb = ", ".join(t for _, _, _, t in qb)
                    conflicts.append(
                        ComplianceConflict(
                            kind="comparison_uncertainty",
                            obligation=obligation or "duration",
                            higher=hi,
                            lower=lo,
                            detail=f"{hi.citation} says [{ta}]; {lo.citation} says [{tb}] "
                            "— incomparable units/qualifiers",
                            same_tier=same_tier,
                        )
                    )
                    continue

            if same_tier:
                continue  # deontic phrasing differences alone are not a same-tier finding here

            ma = {m.group(1).lower() for m in _MODAL_RE.finditer(hi.text)}
            mb = {m.group(1).lower() for m in _MODAL_RE.finditer(lo.text)}
            mandatory = {"shall", "must", "will"}
            weak = {"should", "may", "strive to", "endeavor to"}
            if ma & mandatory and mb and not (mb & mandatory):
                conflicts.append(
                    ComplianceConflict(
                        kind="deontic",
                        obligation=obligation or "mandatoriness",
                        higher=hi,
                        lower=lo,
                        detail=f"{hi.citation} is mandatory ({sorted(ma & mandatory)}); "
                        f"{lo.citation} is non-binding ({sorted(mb & weak) or sorted(mb)})",
                    )
                )
    return conflicts


@dataclass
class TieredAnswer:
    spans: list[Span] = field(default_factory=list)
    conflicts: list[ComplianceConflict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "spans": [
                {"tier": s.tier, "tier_name": TIER_NAMES.get(s.tier, "?"), "citation": s.citation}
                for s in self.spans
            ],
            "conflicts": [c.to_dict() for c in self.conflicts],
        }
