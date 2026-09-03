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
_UNIT_DAYS = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "month": 30,
    "months": 30,
    "year": 365,
    "years": 365,
    "hour": 1 / 24,
    "hours": 1 / 24,
}


def _quant_claims(text: str) -> list[tuple[float, str]]:
    """[(value_in_days, verbatim)] for every numeric-duration claim in a span."""
    out = []
    for m in _QUANT_RE.finditer(text):
        n = int(m.group(1))
        unit = m.group(3).lower()
        out.append((n * _UNIT_DAYS[unit], m.group(0)))
    return out


@dataclass
class ComplianceConflict:
    kind: str  # "quantitative" | "deontic"
    obligation: str  # a short label for what the spans disagree about
    higher: Span
    lower: Span
    detail: str

    def to_dict(self) -> dict:
        return {
            "signal": "COMPLIANCE_CONFLICT",
            "kind": self.kind,
            "obligation": self.obligation,
            "detail": self.detail,
            "higher_authority": {
                "tier": self.higher.tier,
                "tier_name": TIER_NAMES.get(self.higher.tier, "?"),
                "citation": self.higher.citation,
                "text": self.higher.text,
            },
            "lower_authority": {
                "tier": self.lower.tier,
                "tier_name": TIER_NAMES.get(self.lower.tier, "?"),
                "citation": self.lower.citation,
                "text": self.lower.text,
            },
            "resolution": "NOT reconciled — the higher-tier claim governs; the "
            "lower-tier document must be corrected.",
        }


def detect_conflicts(spans: list[Span], obligation: str = "") -> list[ComplianceConflict]:
    """Pairwise across spans of DIFFERENT tiers. Same-tier disagreement is not a
    tier conflict (it is a data-quality issue for one tier to resolve)."""
    conflicts: list[ComplianceConflict] = []
    for i, a in enumerate(spans):
        for b in spans[i + 1 :]:
            if a.tier == b.tier:
                continue
            hi, lo = (a, b) if a.tier < b.tier else (b, a)

            qa = {round(v, 3) for v, _ in _quant_claims(hi.text)}
            qb = {round(v, 3) for v, _ in _quant_claims(lo.text)}
            if qa and qb and qa.isdisjoint(qb):
                ta = ", ".join(t for _, t in _quant_claims(hi.text))
                tb = ", ".join(t for _, t in _quant_claims(lo.text))
                conflicts.append(
                    ComplianceConflict(
                        kind="quantitative",
                        obligation=obligation or "duration",
                        higher=hi,
                        lower=lo,
                        detail=f"{hi.citation} says [{ta}]; {lo.citation} says [{tb}]",
                    )
                )
                continue

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
