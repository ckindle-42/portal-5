"""bully.relation -- the relation engine: grade a stream neighbourhood
against the anchor library (TASK_BULLY_RELATE_AND_INVESTIGATE_V1 A.2).

This *is* the cousin engine, as product (task header): retrieval and
grading are `cousin_engine`'s existing multi-axis machinery, unmodified in
substance. This module's job is narrow -- source the reference side from
`AnchorLibrary` instead of an Organ projection, derive axis weights from the
source's capability annotations (structure leads where a source's
annotations say text is opaque), and shape the result into the
`Relation{verdict, confidence, uncertainty_reasons[], anchors_considered,
axis_contributions}` the investigation frame (J.1) consumes.

Pure compute over injected data: no network, no embeddings service, no
training (COLD). The "semantic" axis here is a cheap deterministic
token-overlap score over anchors already resident in the library, not a
learned embedding lookup -- consistent with A.1's anchors being an
in-memory store, not a vector index.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from . import cousin_engine
from . import signatures as sig_mod
from .anchors import AnchorLibrary

MIN_ANCHOR_COVERAGE = 3
_AXES = tuple(cousin_engine._WEIGHTS)


def _tokenize(text: str) -> set[str]:
    return {tok for tok in text.lower().split() if tok}


def _record_text(record: dict[str, Any]) -> str:
    parts = [
        " ".join(str(x) for x in (record.get("action_sequence") or [])),
        str(record.get("semantic_query") or ""),
        str(record.get("behavior_sequence") or ""),
    ]
    return " ".join(p for p in parts if p)


@dataclass
class AnchorSnapshot:
    """Read-only `snapshot.knn`-shaped adapter over an `AnchorLibrary`, so
    `cousin_engine.retrieve_candidate_axes` can query anchors without an
    Organ/embedding backend. Distance is 1 - token-Jaccard, deterministic
    and network-free (COLD)."""

    library: AnchorLibrary

    def knn(
        self, query: str, k: int = 8, filters: dict[str, Any] | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        query_tokens = _tokenize(query)
        records = self.library.records()
        if filters:
            records = [
                r for r in records if all(r.get(key) == value for key, value in filters.items())
            ]
        scored: list[tuple[dict[str, Any], float]] = []
        for record in records:
            record_tokens = _tokenize(_record_text(record))
            if not query_tokens or not record_tokens:
                distance = 1.0
            else:
                overlap = len(query_tokens & record_tokens) / len(query_tokens | record_tokens)
                distance = 1.0 - overlap
            scored.append((record, distance))
        scored.sort(key=lambda pair: pair[1])
        return scored[:k]


def capability_weights(capabilities: dict[str, bool] | None) -> dict[str, float]:
    """Redistribute `cousin_engine._WEIGHTS` by what the source's capability
    annotations support. An opaque-text source (`semantic_text=False`) has
    its semantic weight zeroed and redistributed to the structural axes
    (behavior/telemetry/attack/context) -- structure leads where text is
    opaque, and the weight mass is conserved (confidence stays comparable
    across sources)."""
    base = dict(cousin_engine._WEIGHTS)
    capabilities = capabilities or {}
    if not capabilities.get("semantic_text", True):
        removed = base.pop("semantic", 0.0)
        remaining_mass = sum(base.values()) or 1.0
        base = {dim: weight + (weight / remaining_mass) * removed for dim, weight in base.items()}
        base["semantic"] = 0.0
    return base


def _uncertainty_reasons(
    assessment,
    *,
    capabilities: dict[str, bool] | None,
    anchor_count: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    decomp = assessment.decomposition.to_dict()
    for axis in _AXES:
        if decomp.get(axis) is None:
            reasons.append(f"missing_dimension:{axis}")
    capabilities = capabilities or {}
    if not capabilities.get("semantic_text", True):
        reasons.append("opaque_entities:semantic_axis_unusable")
    if not capabilities.get("entity_identity", True):
        reasons.append("no_entity_identity:context_axis_weak")
    if anchor_count < MIN_ANCHOR_COVERAGE:
        reasons.append(f"thin_anchor_coverage:{anchor_count}_candidates")
    if assessment.vetoes:
        reasons.append("discriminator_veto:downgraded")
    if assessment.confidence < cousin_engine.MIN_CONFIDENCE_FOR_CLASSIFICATION:
        reasons.append("confidence_below_classification_floor")
    return tuple(reasons)


@dataclass(frozen=True)
class Relation:
    relation_id: str
    verdict: str
    confidence: float
    uncertainty_reasons: tuple[str, ...]
    anchors_considered: tuple[str, ...]
    axis_contributions: dict[str, float | None]
    nearest_knowns: tuple[tuple[str, float], ...]
    distance_profile: dict[str, Any] | None
    assessment: Any = field(repr=False)
    created_at: float = field(default_factory=time.time)


# ── A.3: ANOMALOUS_UNCLASSIFIED as a first-class success ────────────────────

# A "notable" neighbourhood is a *well-observed* one (enough structural
# channels present to trust the distance, not a thin/absent record) that
# still lands far from every anchor. Mere absence of a match (thin coverage,
# few channels) already falls to ANOMALOUS via the confidence floor in
# cousin_engine._classify_relationship -- this is the separate case where
# the data is good and genuinely doesn't match anything known (S3).
NOTABILITY_MIN_CHANNELS = 3


def _is_notable_novelty(assessment) -> bool:
    return (
        assessment.relationship == "DIFFERENT"
        and assessment.nonsemantic_channels >= NOTABILITY_MIN_CHANNELS
        and assessment.confidence >= cousin_engine.MIN_CONFIDENCE_FOR_CLASSIFICATION
    )


def _distance_profile(assessment) -> dict[str, Any]:
    distances = [d for _, d in assessment.nearest_knowns]
    return {
        "composite": assessment.composite,
        "nearest_distance": distances[0] if distances else None,
        "mean_distance": sum(distances) / len(distances) if distances else None,
        "candidates_considered": len(distances),
        "nonsemantic_channels": assessment.nonsemantic_channels,
    }


def relate(
    signature,
    anchor_library: AnchorLibrary,
    *,
    capabilities: dict[str, bool] | None = None,
    coverage: cousin_engine.CoverageView | None = None,
    discriminators: list[str] | None = None,
    k: int = 8,
) -> Relation:
    """Grade `signature` (a stream neighbourhood) against every anchor in
    `anchor_library`, using cousin_engine's multi-axis retrieval + grading,
    weighted by the source's capability annotations."""
    snapshot = AnchorSnapshot(anchor_library)
    candidates = cousin_engine.retrieve_candidate_axes(signature, snapshot, k=k)
    weights = capability_weights(capabilities)
    coverage = coverage or cousin_engine.CoverageView(telemetry_healthy=False)
    assessment = cousin_engine.grade(
        signature,
        candidates,
        coverage,
        discriminators=discriminators,
        weights=weights,
    )
    decomp = assessment.decomposition.to_dict()
    axis_contributions = {
        axis: (weights[axis] * decomp[axis] if decomp.get(axis) is not None else None)
        for axis in _AXES
    }
    anchors_considered = tuple(
        sorted({c["record"].get("record_id", "") for c in candidates.candidates})
    )
    reasons = list(
        _uncertainty_reasons(
            assessment, capabilities=capabilities, anchor_count=len(anchors_considered)
        )
    )

    verdict = assessment.relationship
    notable_novelty = _is_notable_novelty(assessment)
    if notable_novelty:
        # A well-observed neighbourhood that matches nothing known is the
        # correct novel-attack-vector output (S3) -- never silence, never
        # a stretched match to the nearest DIFFERENT anchor.
        verdict = "ANOMALOUS_UNCLASSIFIED"
        reasons.append("novel_behavior:no_anchor_match")

    distance_profile = (
        _distance_profile(assessment) if verdict == "ANOMALOUS_UNCLASSIFIED" else None
    )

    return Relation(
        relation_id=f"rel-{uuid.uuid4().hex[:12]}",
        verdict=verdict,
        confidence=assessment.confidence,
        uncertainty_reasons=tuple(reasons),
        anchors_considered=anchors_considered,
        axis_contributions=axis_contributions,
        nearest_knowns=tuple(assessment.nearest_knowns),
        distance_profile=distance_profile,
        assessment=assessment,
    )


def build_signature_from_neighbourhood(
    episode_view: dict[str, Any], telemetry_view: dict[str, Any] | None = None
):
    """Thin pass-through so callers of this module don't need a separate
    import of `signatures.build_signature` for the common case."""
    return sig_mod.build_signature(episode_view, telemetry_view)
