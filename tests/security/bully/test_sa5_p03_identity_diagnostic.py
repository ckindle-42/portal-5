"""P0.3 -- identity becomes a classified diagnostic, not a sole disqualifier.

Hermetic: `classify_identity_failure` separates each identity-control failure
into corpus-duplicate / scale-mismatch / genuine-discrimination-loss, and
`_identity_control` reports the cause distribution plus the thresholds applied.
"""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.security.core.bully.discovery_bench import (
    _identity_control,
    classify_identity_failure,
)
from portal.modules.security.core.siem.spl_detections import _invalidate_cache


def _assessment(reference_id, composite, relationship="SIMILAR"):
    return SimpleNamespace(
        reference_signature_id=reference_id,
        composite=composite,
        relationship=relationship,
    )


def test_scale_mismatch_when_own_record_recovered_but_above_threshold():
    """Arm B's failure mode: the engine recovers the probe's OWN record as
    nearest, but composite (0.25 * query-vs-doc self-distance) exceeds the
    frozen same_max_distance -- a scale mismatch, rescued by per-space
    thresholds (P0.3)."""
    probe = {"specimen_id": "p-arm-b"}
    cause = classify_identity_failure(
        probe,
        _assessment("p-arm-b", composite=0.11),
        same_max_distance=0.05,
        canonical_text_by_id={"p-arm-b": "text", "p-arm-b-copy": "text"},
    )
    assert cause == "scale-mismatch"


def test_corpus_duplicate_when_text_shared_with_other_record():
    """A probe whose canonical text is duplicated elsewhere cannot be named as
    the exact row by any embedder -- a corpus-composition ambiguity, not an
    embedder defect (P0.3)."""
    probe = {"specimen_id": "p-dup-1"}
    cause = classify_identity_failure(
        probe,
        _assessment("p-dup-2", composite=0.02),
        same_max_distance=0.05,
        canonical_text_by_id={"p-dup-1": "shared", "p-dup-2": "shared", "p-other": "distinct"},
    )
    assert cause == "corpus-duplicate"


def test_genuine_discrimination_loss_when_other_record_outranks_own():
    """Arm A's failure mode: a DIFFERENT near-twin record outranks the probe's
    own row with no shared text -- the model maps near-identical records to
    the same vector. Not rescued by thresholds (P0.3)."""
    probe = {"specimen_id": "p-arm-a"}
    cause = classify_identity_failure(
        probe,
        _assessment("p-twin", composite=0.001),
        same_max_distance=0.05,
        canonical_text_by_id={"p-arm-a": "ta", "p-twin": "tb", "p-twin2": "tc"},
    )
    assert cause == "genuine-discrimination-loss"


def test_identity_control_reports_classified_failures_and_thresholds():
    """`_identity_control` runs the real grade path and reports per-cause
    counts plus the thresholds applied -- identity is a diagnostic, and the
    frozen constants no longer silently disqualify a space (P0.3)."""
    _invalidate_cache()
    from portal.modules.security.core.bully import cousin_engine
    from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot

    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = corpus["specimens"]
    canonical = {s["specimen_id"]: f"text-{i}" for i, s in enumerate(probes)}

    result = _identity_control(
        probes,
        snapshot,
        sample_size=4,
        thresholds={**cousin_engine.DEFAULT_THRESHOLDS, "same_max_distance": 0.05},
        canonical_text_by_id=canonical,
    )
    assert result["checked"] == 4
    assert "by_cause" in result
    assert "thresholds_applied" in result
    assert result["thresholds_applied"]["same_max_distance"] == 0.05
