"""bully.anchors -- the anchor library: a first-class store of known things
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 A.1).

Five anchor kinds, one shape: attack_data episodes (`data.yml` techniques),
advisories (sparse: technique + IOC + context, no action sequence),
detection content + what it covers, confirmed findings from prior
investigations (J.3 writes these back), and benign patterns -- recurring
structures from the non-event corpus (N.1, TASK_BULLY_UNKNOWN_COUSIN_V1).
Every anchor carries provenance, a label basis (why we believe the label),
an anchor-quality grade that can differ across anchors and kinds -- an
anchor without a label basis is stored as `weak`, never rejected (S1:
nothing here gates on quality) -- and a `malice` ("malicious" / "benign" /
"unknown"): a property of the matched *type*, never a separate pipeline
(known types and the normal baseline are different objects; see
`docs/DESIGN_BULLY_UNKNOWN_COUSIN_V1.md`).

Pure in-memory store, no I/O, no SQL (MASTER SS3 boundary: this module is
called by loaders/investigation, it never owns persistence itself). The
`record` payload on every anchor matches `signatures.reference_record_fields`
shape plus a `record_id`, so the relation engine (cousin_engine.grade) can
consume anchors directly as reference records without a translation layer.
"""

from __future__ import annotations

import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

ANCHOR_KINDS: tuple[str, ...] = (
    "attack_episode",
    "advisory",
    "detection_coverage",
    "confirmed_finding",
    "benign_pattern",
)

ANCHOR_GRADES: tuple[str, ...] = ("strong", "moderate", "weak")

MALICE_VALUES: tuple[str, ...] = ("malicious", "benign", "unknown")

# Provenance tiers (G.2 uses these for the raise-confidence / depth-cap /
# revocation rules; defined here because every anchor -- including the ones
# A.1 loads -- carries one from creation, never bolted on later).
PROVENANCE_TIERS: tuple[str, ...] = ("EXTERNAL", "ANALYST_CONFIRMED", "SYSTEM_GENERATED")

_DEFAULT_TIER_BY_KIND: dict[str, str] = {
    "attack_episode": "EXTERNAL",
    "advisory": "EXTERNAL",
    "detection_coverage": "EXTERNAL",
    "confirmed_finding": "ANALYST_CONFIRMED",
    "benign_pattern": "EXTERNAL",
}

# One mechanism, malice is a property of the matched type: every kind has a
# default malice, overridable per-anchor where the kind's own semantics vary
# (a confirmed_finding can go either way depending on its outcome).
_DEFAULT_MALICE_BY_KIND: dict[str, str] = {
    "attack_episode": "malicious",
    "advisory": "malicious",
    "detection_coverage": "malicious",
    "confirmed_finding": "malicious",
    "benign_pattern": "benign",
}

# Kinds whose label basis, when present, is treated as strong evidence
# (an authoritative manifest or an operator decision) rather than a sparse
# or inferred signal.
_STRONG_KINDS: frozenset[str] = frozenset({"attack_episode", "confirmed_finding"})


def _grade_anchor(kind: str, label_basis: str | None) -> str:
    if not label_basis:
        return "weak"
    return "strong" if kind in _STRONG_KINDS else "moderate"


@dataclass(frozen=True)
class Anchor:
    anchor_id: str
    kind: str
    record: dict[str, Any]
    provenance_tier: str
    label_basis: str | None
    grade: str
    source_id: str
    malice: str = "unknown"
    derived_from: tuple[str, ...] = ()
    generation_depth: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_anchor(
    kind: str,
    record: dict[str, Any],
    *,
    source_id: str,
    label_basis: str | None = None,
    provenance_tier: str | None = None,
    malice: str | None = None,
    derived_from: tuple[str, ...] = (),
    generation_depth: int = 0,
    anchor_id: str | None = None,
) -> Anchor:
    if kind not in ANCHOR_KINDS:
        raise ValueError(f"unknown anchor kind: {kind!r}")
    tier = provenance_tier or _DEFAULT_TIER_BY_KIND[kind]
    if tier not in PROVENANCE_TIERS:
        raise ValueError(f"unknown provenance tier: {tier!r}")
    resolved_malice = malice or _DEFAULT_MALICE_BY_KIND[kind]
    if resolved_malice not in MALICE_VALUES:
        raise ValueError(f"unknown malice value: {resolved_malice!r}")
    record = dict(record)
    record.setdefault("record_id", anchor_id or f"anchor-{uuid.uuid4().hex[:12]}")
    record.setdefault("signature_id", record["record_id"])
    return Anchor(
        anchor_id=anchor_id or record["record_id"],
        kind=kind,
        record=record,
        provenance_tier=tier,
        label_basis=label_basis,
        grade=_grade_anchor(kind, label_basis),
        source_id=source_id,
        malice=resolved_malice,
        derived_from=tuple(derived_from),
        generation_depth=generation_depth,
    )


class AnchorLibrary:
    """The known side: growable, queryable by kind, never gated on quality."""

    def __init__(self) -> None:
        self._anchors: dict[str, Anchor] = {}

    def __len__(self) -> int:
        return len(self._anchors)

    def add(self, anchor: Anchor) -> Anchor:
        self._anchors[anchor.anchor_id] = anchor
        return anchor

    def get(self, anchor_id: str) -> Anchor | None:
        return self._anchors.get(anchor_id)

    def all(self) -> tuple[Anchor, ...]:
        return tuple(self._anchors.values())

    def by_kind(self, kind: str) -> tuple[Anchor, ...]:
        return tuple(a for a in self._anchors.values() if a.kind == kind)

    def records(self, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """Reference-record view for the relation engine (A.2): every
        anchor's `record`, optionally filtered by kind."""
        selected = (
            self._anchors.values()
            if kinds is None
            else (a for a in self._anchors.values() if a.kind in kinds)
        )
        return [a.record for a in selected]

    def composition(self) -> dict[str, dict[str, int]]:
        """Kind -> grade -> count, for the M.3 anchor-library-composition
        report."""
        out: dict[str, dict[str, int]] = {kind: {} for kind in ANCHOR_KINDS}
        for anchor in self._anchors.values():
            bucket = out.setdefault(anchor.kind, {})
            bucket[anchor.grade] = bucket.get(anchor.grade, 0) + 1
        return out

    # ── loaders: one per anchor kind ─────────────────────────────────────

    def load_attack_episode(
        self,
        *,
        source_id: str,
        record: dict[str, Any],
        techniques: tuple[str, ...] = (),
        label_basis: str | None = "data_yml",
    ) -> Anchor:
        """attack_data episode: `data.yml`-declared techniques are the
        label basis when present; an episode with no manifest techniques is
        stored `weak`, not dropped (S1)."""
        payload = dict(record)
        if techniques:
            payload.setdefault("attack_mappings", [{"technique_id": t} for t in techniques])
        basis = label_basis if techniques else None
        return self.add(
            make_anchor("attack_episode", payload, source_id=source_id, label_basis=basis)
        )

    def load_advisory(
        self,
        *,
        source_id: str,
        technique: str | None,
        ioc: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        label_basis: str | None = None,
    ) -> Anchor:
        """Advisory: sparse signature -- technique + IOC + context only, no
        action sequence (S1: an advisory naming no technique is still
        usable, just weaker)."""
        payload: dict[str, Any] = {
            "context_topology": dict(context or {}),
            "artifacts": dict(ioc or {}),
        }
        if technique:
            payload["attack_mappings"] = [{"technique_id": technique}]
            basis = label_basis or "vendor_advisory"
        else:
            basis = None
        return self.add(make_anchor("advisory", payload, source_id=source_id, label_basis=basis))

    def load_detection_coverage(
        self,
        *,
        source_id: str,
        detection_id: str,
        techniques: tuple[str, ...] = (),
        telemetry_shape: dict[str, Any] | None = None,
        label_basis: str | None = "detection_mapping",
    ) -> Anchor:
        """Detection content + what it covers."""
        payload: dict[str, Any] = {
            "record_id": detection_id,
            "telemetry_shape": dict(telemetry_shape or {}),
        }
        if techniques:
            payload["attack_mappings"] = [{"technique_id": t} for t in techniques]
        basis = label_basis if techniques else None
        return self.add(
            make_anchor(
                "detection_coverage",
                payload,
                source_id=source_id,
                label_basis=basis,
                anchor_id=detection_id,
            )
        )

    def load_confirmed_finding(
        self,
        *,
        source_id: str,
        record: dict[str, Any],
        outcome: str,
        analyst_confirmed: bool,
        derived_from: tuple[str, ...] = (),
        generation_depth: int = 0,
    ) -> Anchor:
        """A prior investigation's outcome, written back (S6/J.3). Analyst
        review is the label basis; an un-reviewed (system-generated)
        outcome is stored `weak` and at `SYSTEM_GENERATED` tier -- it still
        enters the library, it just cannot raise confidence (G.2)."""
        payload = dict(record)
        payload["outcome"] = outcome
        tier = "ANALYST_CONFIRMED" if analyst_confirmed else "SYSTEM_GENERATED"
        basis = "analyst_decision" if analyst_confirmed else None
        return self.add(
            make_anchor(
                "confirmed_finding",
                payload,
                source_id=source_id,
                label_basis=basis,
                provenance_tier=tier,
                derived_from=derived_from,
                generation_depth=generation_depth,
            )
        )

    def load_benign_pattern(
        self,
        *,
        source_id: str,
        record: dict[str, Any],
        recurrence_count: int,
        label_basis: str | None = "recurring_corpus_structure",
    ) -> Anchor:
        """A benign type: a recurring structure found in the non-event
        corpus data (N.1). That data is a first-class design input, not
        contamination -- known-benign types are what makes "this is exactly
        a known benign type" sayable, which is what turns `BENIGN_CLOSE`
        write-back (L.1) from dead wiring into live suppression. Grade
        follows the same rule as every other kind: no `label_basis` (a
        pattern seen too rarely to trust) stores `weak`, never dropped."""
        payload = dict(record)
        payload["recurrence_count"] = recurrence_count
        basis = label_basis if recurrence_count > 0 else None
        return self.add(
            make_anchor(
                "benign_pattern",
                payload,
                source_id=source_id,
                label_basis=basis,
                malice="benign",
            )
        )


def derive_recurring_benign_patterns(
    records: list[dict[str, Any]],
    *,
    min_recurrence: int = 3,
) -> list[dict[str, Any]]:
    """Structural patterns worth loading as benign types: group non-event
    corpus records by their behavioural-class shape (reusing U.1's
    structural grouping, not a bespoke clustering) and keep the ones that
    recur at least `min_recurrence` times. A one-off structure is not a
    "type" -- it is noise, and is left out rather than stored `weak` under a
    misleading pattern label.

    Returns plain records (`action_sequence` = the recurring class shape,
    `recurrence_count` = how often it recurred) ready for
    `AnchorLibrary.load_benign_pattern`. Pure compute, no I/O -- the caller
    supplies the corpus.
    """
    from . import artifact_graph as ag

    graph = ag.build_graph(records)
    shape_counts: Counter[tuple[str, ...]] = Counter()
    for unit in ag.enumerate_units(graph, levels=("L1_ARTIFACT", "L2_ENTITY")):
        shape = tuple(unit.structural_signature.get("class_sequence") or ())
        if shape:
            shape_counts[shape] += 1

    patterns: list[dict[str, Any]] = []
    for shape, count in shape_counts.items():
        if count < min_recurrence:
            continue
        patterns.append(
            {
                "action_sequence": list(shape),
                "recurrence_count": count,
            }
        )
    return patterns
