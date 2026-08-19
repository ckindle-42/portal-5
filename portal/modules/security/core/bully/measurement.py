"""bully.measurement -- the measurement plane, scoped
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 M.1).

Score only where an anchor provides real ground truth (S5): a relation
whose matched anchor has no label basis, or whose provenance can't raise
confidence (provenance.can_raise_confidence), is unscored -- reported, not
counted wrong, and still fully used operationally. Everything scoreable
also carries the joint relation x response product metric
(`cousin_engine.product_band`, unchanged: SAME x MISSED is a regression).
Lineage groups collapse corroboration across sources that share an
underlying feed, so overlapping sources can never double-corroborate one
claim; pairwise timeline/entity properties are read straight off the
existing `data_plane.SourceProfile` fields, never stored as a per-source
scalar.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import provenance as provenance_mod
from .anchors import AnchorLibrary


def score_eligible(relation: Any, anchor_library: AnchorLibrary) -> bool:
    """A relation is score-eligible only if it matched a real anchor with a
    label basis whose provenance can actually ground truth (EXTERNAL/
    ANALYST_CONFIRMED, within the G.2 depth cap). Everything else --
    including a perfectly good SAME/SIMILAR match to a weak or
    SYSTEM_GENERATED anchor -- is unscored, never silently counted."""
    anchor_id = relation.assessment.reference_signature_id
    if not anchor_id:
        return False
    anchor = anchor_library.get(anchor_id)
    if anchor is None or anchor.label_basis is None:
        return False
    return provenance_mod.can_raise_confidence(anchor)


@dataclass(frozen=True)
class ScoredRow:
    relation: Any
    ground_truth: str
    correct: bool


@dataclass(frozen=True)
class AccuracyReport:
    scored: tuple[ScoredRow, ...]
    unscored_count: int
    accuracy: float | None

    @property
    def scored_count(self) -> int:
        return len(self.scored)

    @property
    def coverage(self) -> float:
        total = self.scored_count + self.unscored_count
        return self.scored_count / total if total else 0.0


def compute_accuracy(
    rows: list[tuple[Any, AnchorLibrary, str]],
) -> AccuracyReport:
    """`rows` is (relation, anchor_library, ground_truth_verdict). A row's
    correctness is `relation.verdict == ground_truth_verdict`; unscored
    rows (score_eligible == False) are excluded from accuracy entirely --
    never counted as wrong -- but still counted toward `coverage`."""
    scored: list[ScoredRow] = []
    unscored = 0
    for relation, anchor_library, ground_truth in rows:
        if score_eligible(relation, anchor_library):
            scored.append(ScoredRow(relation, ground_truth, relation.verdict == ground_truth))
        else:
            unscored += 1
    accuracy = (sum(1 for r in scored if r.correct) / len(scored)) if scored else None
    return AccuracyReport(scored=tuple(scored), unscored_count=unscored, accuracy=accuracy)


def _relation_ranked_cousins(relation: Any) -> tuple[tuple[str, float], ...]:
    """Provoked `Relation` carries `nearest_knowns`; observed-mode
    `CousinRelation` carries `ranked_cousins` -- same (anchor_id, distance)
    shape under a different name (TASK_BULLY_COUSIN_RELATION_V1 C.3a)."""
    ranked = getattr(relation, "nearest_knowns", None)
    if ranked is None:
        ranked = getattr(relation, "ranked_cousins", None)
    return tuple(ranked or ())


def ranked_external_cousins(
    relation: Any, anchor_library: AnchorLibrary, *, top_k: int = 5
) -> tuple[tuple[str, float], ...]:
    """`ranked_cousins`/`nearest_knowns` filtered to EXTERNAL-tier anchors
    only -- the scoring-eligible neighbour set (C.3a). `SYSTEM_GENERATED`
    anchors (the system's own prior write-back) must not displace real
    `EXTERNAL` anchors in the neighbour set used for scoring, even though
    they may legitimately be the *nearest* match overall."""
    out: list[tuple[str, float]] = []
    for anchor_id, distance in _relation_ranked_cousins(relation):
        anchor = anchor_library.get(anchor_id)
        if anchor is not None and anchor.provenance_tier == "EXTERNAL":
            out.append((anchor_id, distance))
    return tuple(out[:top_k])


@dataclass(frozen=True)
class CompoundingReport:
    """The compounding claim, scored external-only (G.3, C.3a). A row is
    scored only when its nearest *EXTERNAL* cousin can be identified --
    never against the relation's raw nearest match, which is frequently the
    system's own prior `SYSTEM_GENERATED` output once write-back is live,
    and is not itself score-eligible ground truth."""

    scored: tuple[ScoredRow, ...]
    external_scored_count: int
    total_rows: int
    coverage: float

    @property
    def valid(self) -> bool:
        """A compounding claim resting on zero external rows is reported
        INVALID, never as a result."""
        return self.external_scored_count > 0


def compounding_accuracy(
    rows: list[tuple[Any, AnchorLibrary, str]],
) -> CompoundingReport:
    """`rows` is (relation, anchor_library, ground_truth_anchor_id). Scores
    each row against its nearest EXTERNAL-tier cousin, not its raw nearest
    match -- see `ranked_external_cousins`. Rows with no EXTERNAL cousin in
    their ranked neighbours are excluded, same as `compute_accuracy`'s
    unscored rows, but tracked separately here as the compounding-specific
    coverage signal the M.3 published table omitted."""
    scored: list[ScoredRow] = []
    for relation, anchor_library, ground_truth in rows:
        external = ranked_external_cousins(relation, anchor_library)
        if not external:
            continue
        best_external_id, _distance = external[0]
        scored.append(ScoredRow(relation, ground_truth, best_external_id == ground_truth))
    total_rows = len(rows)
    external_scored_count = len(scored)
    coverage = external_scored_count / total_rows if total_rows else 0.0
    return CompoundingReport(
        scored=tuple(scored),
        external_scored_count=external_scored_count,
        total_rows=total_rows,
        coverage=coverage,
    )


def shuffled_label_control(
    rows: list[tuple[Any, AnchorLibrary, str]], *, seed: int = 0
) -> tuple[float | None, float | None]:
    """P7.4 shuffled-label control: shuffling *ground-truth* labels among
    the scored rows must collapse accuracy toward chance -- if it doesn't,
    the accuracy number isn't measuring what it claims to. Returns
    (real_accuracy, shuffled_accuracy)."""
    real = compute_accuracy(rows)
    rng = random.Random(seed)
    eligible_indices = [i for i, (r, lib, _g) in enumerate(rows) if score_eligible(r, lib)]
    labels = [rows[i][2] for i in eligible_indices]
    rng.shuffle(labels)
    shuffled_rows = list(rows)
    for idx, label in zip(eligible_indices, labels, strict=True):
        relation, lib, _old = shuffled_rows[idx]
        shuffled_rows[idx] = (relation, lib, label)
    shuffled = compute_accuracy(shuffled_rows)
    return real.accuracy, shuffled.accuracy


# ── lineage: overlapping sources cannot corroborate ─────────────────────────


@dataclass(frozen=True)
class LineageGroups:
    """source_id -> lineage_id. Sources absent from the mapping are their
    own lineage (independent by default)."""

    groups: dict[str, str] = field(default_factory=dict)

    def lineage_of(self, source_id: str) -> str:
        return self.groups.get(source_id, source_id)


def independent_sources(groups: LineageGroups, source_ids: list[str]) -> set[str]:
    """Collapse `source_ids` sharing a lineage to one representative each --
    the set of *independent* corroborators."""
    representatives: dict[str, str] = {}
    for source_id in source_ids:
        representatives.setdefault(groups.lineage_of(source_id), source_id)
    return set(representatives.values())


def corroboration_count(groups: LineageGroups, source_ids: list[str]) -> int:
    """Two sources in one lineage set can never corroborate each other --
    they count once, not twice."""
    return len(independent_sources(groups, source_ids))


# ── pairwise relational properties (read off the existing data model) ──────


def pairwise_timeline_comparable(profile_a: Any, profile_b: Any) -> bool:
    """Never a global per-source scalar: both sides must independently
    declare their time binding comparable with other sources."""
    return bool(
        profile_a.time_binding.comparable_with_other_sources
        and profile_b.time_binding.comparable_with_other_sources
    )


def pairwise_entity_linkable(profile_a: Any, profile_b: Any) -> bool:
    """True only if an explicit EntityLink connects these two specific
    sources -- never inferred from each source's capability flag alone."""
    ids = {profile_a.source_id, profile_b.source_id}
    for link in (*profile_a.entity_links, *profile_b.entity_links):
        if {link.left_source, link.right_source} == ids:
            return True
    return False
