"""bully.embedding_spaces -- per-embedding-space threshold derivation (P0.2).

``cousin_engine.DEFAULT_THRESHOLDS["same_max_distance"]`` was a bare
constant fit to the retired harrier space's cosine scale (re-fit to EG2+V3
under B1.4, 2026-10-08).  Arm B failed identity 25/25 purely on scale
mismatch: EmbeddingGemma's asymmetric task prefixes put query-form-vs-doc-form
self-distance at ~0.3-0.45, so the semantic channel's contribution to the
composite outran the frozen threshold regardless of retrieval quality.

This module derives same/similar/new per embedding space from that space's
self-distance and near/far distributions, expressed on the engine's composite
scale (the semantic channel carries ``_WEIGHTS["semantic"]``).  The reference
space must reproduce the frozen thresholds within tolerance -- the derivation
is a portability fix, not a tuning pass (A7, P0.2).

The composite for a self-pair is ``semantic_weight * d_self`` (all other channels are
identical for a probe and its own record, so they contribute zero distance).
Near/far pairs differ in the semantic channel too, so the derived thresholds
shift by ``semantic_weight * (d - reference)`` relative to the frozen values.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from . import cousin_engine

Vector = Sequence[float]

# Frozen thresholds calibrated on the incumbent (harrier, symmetric) space.
FROZEN_THRESHOLDS = dict(cousin_engine.DEFAULT_THRESHOLDS)

# Reference self/near/far p95 raw cosine distances (the semantic channel's scale anchor),
# re-measured 2026-10-08 on the primary space -- EG2 (`:8946/embed`, sentence-similarity,
# symmetric query-role on both sides) over the deduplicated SPECIMEN_CORPUS_V3 parents
# (64-text sample, `measure_distances`; reports/bully_b1/20261008T195439Z/THRESHOLDS_B1_4.md).
# self p95 is 0 (the space is symmetric), near p95 0.1336, far p95 0.1630 -- both above the
# retired harrier space's 0.073/0.064, so the upward-only clamp below never binds for the
# primary space; it stays as the anti-tuning guard for hypothetical tighter future spaces.
_INCUMBENT_SELF_P95 = 0.0
_INCUMBENT_NEAR_P95 = 0.1336
_INCUMBENT_FAR_P95 = 0.1630

# A derived threshold may only move the frozen values upward (the portability
# fix rescues scale mismatches; it never tightens a space that happens to be
# more discriminative, which would be tuning).
_SEMANTIC_WEIGHT = cousin_engine._WEIGHTS["semantic"]  # noqa: SLF001 -- same package

DERIVED_THRESHOLDS_SCHEMA = "EMBEDDING_SPACE_THRESHOLDS_V1"
TOLERANCE = 0.02  # incumbent reproduction tolerance (composite scale)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))])


def measure_distances(
    *,
    embed_fn: Callable[[list[str]], Sequence[Vector]],
    query_embed_fn: Callable[[list[str]], Sequence[Vector]] | None = None,
    texts: list[str],
    near_pairs: list[tuple[int, int]] | None = None,
    far_pairs: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Measure self/near/far raw cosine-distance distributions for a space.

    ``embed_fn(texts) -> list[vectors]`` embeds in document form (the upsert
    path); ``query_embed_fn`` embeds in query form (the knn path) and defaults
    to ``embed_fn`` for symmetric spaces.  ``near_pairs``/``far_pairs`` are
    index pairs into ``texts`` (defaults synthesize deterministic pairs).
    """
    doc = embed_fn(list(texts))
    query = query_embed_fn(list(texts)) if query_embed_fn else doc

    def dist(i: int, j: int) -> float:
        a, b = doc[i], query[j]
        return 1.0 - sum(x * y for x, y in zip(a, b, strict=True)) / max(
            1e-12,
            math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)),
        )

    n = len(texts)
    if near_pairs is None:
        near_pairs = [(i, min(i + 1, n - 1)) for i in range(0, n - 1, 2)]
    if far_pairs is None:
        far_pairs = [(i, (n // 2 + i % 16) % n) for i in range(0, n, 7)]

    self_dist = [dist(i, i) for i in range(n)]
    near_dist = [dist(i, j) for i, j in near_pairs]
    far_dist = [dist(i, j) for i, j in far_pairs]
    return {
        "self": {
            "p50": _p95(sorted(self_dist)[: max(1, len(self_dist) // 2)]),
            "p95": _p95(self_dist),
            "n": len(self_dist),
        },
        "near": {
            "p50": _p95(sorted(near_dist)[: max(1, len(near_dist) // 2)]),
            "p95": _p95(near_dist),
            "n": len(near_dist),
        },
        "far": {
            "p50": _p95(sorted(far_dist)[: max(1, len(far_dist) // 2)]),
            "p95": _p95(far_dist),
            "n": len(far_dist),
        },
    }


@dataclass(frozen=True)
class DerivedThresholds:
    """Per-embedding-space thresholds, versioned with the embedding version."""

    schema: str
    embedding_version: str
    thresholds_version: str
    same_max_distance: float
    similar_max_distance: float
    new_max_distance: float
    distributions: dict[str, Any]
    incumbent_reproduced: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_thresholds(
    distributions: dict[str, Any],
    *,
    embedding_version: str,
    frozen: dict[str, float] | None = None,
    tolerance: float = TOLERANCE,
) -> DerivedThresholds:
    """Derive same/similar/new from a space's measured self/near/far p95s.

    Thresholds are on the engine's composite scale: the semantic channel
    contributes ``0.25 * d``, and all other channels are space-invariant, so a
    space with self-distance ``d_self`` needs ``same_max_distance >=
    0.25*d_self`` for a probe to recover its own record as SAME.  The shift
    relative to the incumbent reference is applied to the frozen values.  For
    the incumbent the shift is ~0 and the frozen values reproduce within
    ``tolerance``.
    """
    frozen = frozen or FROZEN_THRESHOLDS
    self_p95 = float(distributions["self"]["p95"])
    near_p95 = float(distributions["near"]["p95"])
    far_p95 = float(distributions["far"]["p95"])

    same_shift = _SEMANTIC_WEIGHT * max(0.0, self_p95 - _INCUMBENT_SELF_P95)
    near_shift = _SEMANTIC_WEIGHT * max(0.0, near_p95 - _INCUMBENT_NEAR_P95)
    far_shift = _SEMANTIC_WEIGHT * max(0.0, far_p95 - _INCUMBENT_FAR_P95)

    derived = {
        "same_max_distance": round(frozen["same_max_distance"] + same_shift, 4),
        "similar_max_distance": round(frozen["similar_max_distance"] + near_shift, 4),
        "new_max_distance": round(frozen["new_max_distance"] + far_shift, 4),
    }
    # Monotonicity guard: same < similar < new must hold regardless of the
    # space's geometry (a pathological far-p95 below near-p95 must not invert).
    derived["similar_max_distance"] = round(
        max(derived["similar_max_distance"], derived["same_max_distance"] + 0.01), 4
    )
    derived["new_max_distance"] = round(
        max(derived["new_max_distance"], derived["similar_max_distance"] + 0.01), 4
    )

    incumbent_reproduced = all(abs(derived[key] - frozen[key]) <= tolerance for key in frozen)
    return DerivedThresholds(
        schema=DERIVED_THRESHOLDS_SCHEMA,
        embedding_version=embedding_version,
        thresholds_version=f"bully-cousin-thresholds-{embedding_version}",
        same_max_distance=derived["same_max_distance"],
        similar_max_distance=derived["similar_max_distance"],
        new_max_distance=derived["new_max_distance"],
        distributions=distributions,
        incumbent_reproduced=incumbent_reproduced,
    )
