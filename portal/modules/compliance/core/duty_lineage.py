"""Semantic duty identity and cross-revision lineage (foundation task P3).

Lineage answers: is the CIP-007-7.1 duty that happens to share Part 2.2's
number the *same duty* as CIP-007-6's Part 2.2? The source never says so
directly — and part numbering cannot be the identity rule ("without assuming
Part numbering proves semantic identity"). Identity is computed from duty-text
correspondence after folding the revisions' controlled-terminology drift
("cyber security patches" → "security patches", "Applicable Systems" →
"applicable Cyber Assets", "BCS" → "BES Cyber Systems"), and recorded as a
derived assertion with its derivation string — never as a source fact.

Concept identities are stable as the lineage grows: a concept is rooted at its
oldest member duty, so a future CIP-007-8 pairing with a 7.1 duty joins the
existing concept instead of minting a new one.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

#: terminology drift folds, applied before comparison. Each entry maps a
#: later-revision term to its earlier-revision equivalent; the fold list is
#: versioned because lineage results are only comparable under the same
#: normalizer.
_TERMINOLOGY_FOLDS: tuple[tuple[str, str], ...] = (
    ("cyber security patches", "security patches"),
    ("cyber security patch", "security patch"),
    ("applicable systems", "applicable cyber assets"),
    ("bcs", "bes cyber systems"),
)
_NORMALIZER_VERSION = "terminology-fold/1"
_MATCH_THRESHOLD = 0.75
#: derivation string recorded on every concept — lineage rows are only
#: comparable under the same normalizer + threshold.
DERIVATION = (
    f"computed-text-equivalence/1 ({_NORMALIZER_VERSION}, "
    f"threshold={_MATCH_THRESHOLD}, autojunk=off)"
)


def normalize_duty_text(text: str) -> str:
    lowered = text.lower()
    for later, earlier in _TERMINOLOGY_FOLDS:
        lowered = lowered.replace(later, earlier)
    return " ".join("".join(c if c.isalnum() else " " for c in lowered).split())


def similarity(a_text: str, b_text: str) -> float:
    return SequenceMatcher(
        None, normalize_duty_text(a_text), normalize_duty_text(b_text), autojunk=False
    ).ratio()


@dataclass
class DutyHandle:
    """One revision-specific duty offered to the pairing algorithm."""

    node_id: str  # e.g. "CIP-007-6 R2 Part 2.2" — the duty's revision identity
    standard: str  # "CIP-007"
    text: str  # the verbatim duty text

    @property
    def revision_order(self) -> tuple[str, str]:
        """(standard, version) — earlier versions root the concept."""
        m = re.match(rf"{re.escape(self.standard)}-([\w.]+)\s", self.node_id + " ")
        return (self.standard, m.group(1) if m else "0")


@dataclass
class LineagePair:
    a: DutyHandle
    b: DutyHandle
    score: float

    @property
    def older(self) -> DutyHandle:
        return min((self.a, self.b), key=lambda d: d.revision_order)


@dataclass
class Concept:
    concept_id: str
    family: str
    label: str
    derivation: str
    members: list[str] = field(default_factory=list)


def pair_duties(
    duties_a: list[DutyHandle],
    duties_b: list[DutyHandle],
    *,
    threshold: float = _MATCH_THRESHOLD,
) -> tuple[list[LineagePair], list[DutyHandle], list[DutyHandle]]:
    """Greedy mutual-best pairing by normalized-text similarity.

    Part numbers are carried on the handles for inspection but are never a
    matching feature. Returns (pairs, unpaired_a, unpaired_b); every duty
    appears exactly once across the three lists.
    """
    scored: list[tuple[float, int, int]] = []
    for i, a in enumerate(duties_a):
        for j, b in enumerate(duties_b):
            scored.append((similarity(a.text, b.text), i, j))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs: list[LineagePair] = []
    for score, i, j in scored:
        if score < threshold or i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append(LineagePair(a=duties_a[i], b=duties_b[j], score=score))
    unpaired_a = [d for i, d in enumerate(duties_a) if i not in used_a]
    unpaired_b = [d for j, d in enumerate(duties_b) if j not in used_b]
    return pairs, unpaired_a, unpaired_b


def _concept_id(anchor_node_id: str) -> str:
    return "concept-" + hashlib.sha256(anchor_node_id.encode()).hexdigest()[:16]


def _concept_label(anchor: DutyHandle) -> str:
    return f"{anchor.node_id} — {anchor.text[:48]}…"


def assign_concepts(
    pairs: list[LineagePair],
    unpaired: list[DutyHandle],
    *,
    prior_concepts: dict[str, str] | None = None,
) -> list[Concept]:
    """One concept per duty, joined across paired duties.

    ``prior_concepts`` maps node_id -> concept_id for duties whose concepts
    were assigned in an earlier run; a paired duty with a prior concept joins
    it (lineage grows without minting duplicates). A pair of brand-new duties
    is rooted at the older revision. Unpaired duties root their own concept —
    a duty with no counterpart is new in its revision, and that is a result,
    not an error.
    """
    prior = prior_concepts or {}
    assignment: dict[str, str] = {}  # node_id -> concept_id
    anchors: dict[str, DutyHandle] = {}  # concept_id -> rooting duty

    def _join(duty: DutyHandle, concept_id: str) -> None:
        prior_id = prior.get(duty.node_id)
        if prior_id and prior_id != concept_id:
            raise ValueError(
                f"lineage conflict: {duty.node_id} holds concept {prior_id} "
                f"but pairing assigns {concept_id}"
            )
        assignment[duty.node_id] = concept_id

    for pair in pairs:
        anchor = pair.older
        concept_id = prior.get(anchor.node_id) or _concept_id(anchor.node_id)
        anchors.setdefault(concept_id, anchor)
        _join(pair.a, concept_id)
        _join(pair.b, concept_id)
    for duty in unpaired:
        if duty.node_id in assignment:
            continue
        concept_id = prior.get(duty.node_id) or _concept_id(duty.node_id)
        anchors.setdefault(concept_id, duty)
        _join(duty, concept_id)

    merged: dict[str, Concept] = {}
    for node_id, concept_id in assignment.items():
        anchor = anchors[concept_id]
        row = merged.setdefault(
            concept_id,
            Concept(concept_id, anchor.standard, _concept_label(anchor), DERIVATION, []),
        )
        row.members.append(node_id)
    return list(merged.values())
