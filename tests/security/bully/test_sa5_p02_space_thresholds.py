"""P0.2 -- per-embedding-space threshold derivation (TASK_BULLY_SA5).

Hermetic: the derivation maps measured self/near/far distributions onto the
engine's composite scale via the semantic channel weight; the incumbent
(harrier, symmetric) space reproduces its frozen thresholds within tolerance;
an asymmetric space (query-vs-doc self-distance) raises `same_max_distance`
so a probe can recover its own record; monotonicity same < similar < new
holds for pathological distributions.
"""

from __future__ import annotations

from portal.modules.security.core.bully import cousin_engine
from portal.modules.security.core.bully.embedding_spaces import (
    DERIVED_THRESHOLDS_SCHEMA,
    FROZEN_THRESHOLDS,
    TOLERANCE,
    derive_thresholds,
    measure_distances,
)

_INCUMBENT_LIKE = {
    "self": {"p95": 0.0, "p50": 0.0, "n": 64},
    "near": {"p95": 0.073, "p50": 0.047, "n": 32},
    "far": {"p95": 0.064, "p50": 0.054, "n": 10},
}

_ASYMMETRIC = {
    "self": {"p95": 0.427, "p50": 0.388, "n": 64},
    "near": {"p95": 0.056, "p50": 0.005, "n": 32},
    "far": {"p95": 0.056, "p50": 0.021, "n": 10},
}


def test_incumbent_space_reproduces_frozen_thresholds_within_tolerance():
    """P0.2: the incumbent harrier space (symmetric, self-distance ~0) must
    reproduce its frozen thresholds within tolerance -- a portability fix,
    never a re-tune."""
    derived = derive_thresholds(_INCUMBENT_LIKE, embedding_version="sentence-transformers-v1")
    assert derived.schema == DERIVED_THRESHOLDS_SCHEMA
    assert derived.incumbent_reproduced is True
    for key in ("same_max_distance", "similar_max_distance", "new_max_distance"):
        assert abs(getattr(derived, key) - FROZEN_THRESHOLDS[key]) <= TOLERANCE
    assert derived.thresholds_version == "bully-cousin-thresholds-sentence-transformers-v1"


def test_asymmetric_space_raises_same_max_distance_for_own_record():
    """P0.2: a space whose query-vs-doc self-distance is ~0.43 (Arm B) must
    raise `same_max_distance` so a probe recovers its own record as SAME --
    the scale mismatch that failed Arm B identity 25/25."""
    derived = derive_thresholds(_ASYMMETRIC, embedding_version="llamacpp-embeddinggemma-300m-q8")
    semantic_self = 0.25 * _ASYMMETRIC["self"]["p95"]
    assert derived.same_max_distance >= semantic_self + FROZEN_THRESHOLDS["same_max_distance"]
    assert derived.same_max_distance > FROZEN_THRESHOLDS["same_max_distance"]
    assert derived.incumbent_reproduced is False  # it is not the incumbent


def test_derived_thresholds_stay_monotonic_for_pathological_distributions():
    """A space whose far-p95 sits below near-p95 (noise) must not invert the
    band order -- same < similar < new always holds (guarded derivation)."""
    noisy = {
        "self": {"p95": 0.5, "p50": 0.4, "n": 64},
        "near": {"p95": 0.6, "p50": 0.5, "n": 32},
        "far": {"p95": 0.2, "p50": 0.1, "n": 10},
    }
    derived = derive_thresholds(noisy, embedding_version="noisy-space")
    assert derived.same_max_distance < derived.similar_max_distance
    assert derived.similar_max_distance < derived.new_max_distance


def test_measure_distances_computes_self_near_far_from_embed_fn():
    """measure_distances uses the embed fn to compute cosine distances; near
    pairs are closer than far pairs on a deterministic vector space."""
    n = 8

    def embed_fn(texts):
        # one-hot-ish vectors: text i -> unit vector along axis i
        return [[1.0 if j == i % n else 0.0 for j in range(n)] for i in range(len(texts))]

    texts = [f"text-{i}" for i in range(n)]
    near_pairs = [(i, i + 1) for i in range(0, n - 1, 2)]
    far_pairs = [(i, (i + 4) % n) for i in range(0, n, 2)]
    dists = measure_distances(
        embed_fn=embed_fn, texts=texts, near_pairs=near_pairs, far_pairs=far_pairs
    )
    # self distance is 0 (same vector)
    assert dists["self"]["p95"] == 0.0
    # near pairs (adjacent axes) are farther apart than self, far pairs too
    assert dists["near"]["p95"] > 0.0
    assert dists["far"]["p95"] > 0.0


def test_semantic_weight_matches_engine():
    """The derivation's composite-scale conversion must use the engine's own
    semantic channel weight -- otherwise the scale model is wrong."""
    assert cousin_engine._WEIGHTS["semantic"] == 0.25
