"""C.3 -- measurement and guards read the true quantity, not a schema-shape
constant: (a) compounding is scored external-only, (b) uncertainty variance
is checked within a source, not merely across sources, (c) calibration binds
to CousinRelation.confidence, and an over-confident engine blocks release."""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.security.core.bully import calibration, degeneracy, measurement
from portal.modules.security.core.bully.anchors import AnchorLibrary


def _relation_stub(anchor_id, distance=0.1, reasons=()):
    return SimpleNamespace(
        ranked_cousins=((anchor_id, distance),) if anchor_id else (),
        uncertainty_reasons=reasons,
    )


def _library_with(external_id="ext-1", system_id="sys-1"):
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["a"], "record_id": external_id},
        techniques=("T1059",),
    )
    lib.load_confirmed_finding(
        record={"action_sequence": ["a"], "record_id": system_id},
        source_id="observed:x",
        outcome="ESCALATE",
        analyst_confirmed=False,
    )
    return lib


# ── C.3(a): compounding scored external-only ────────────────────────────────


def test_compounding_scores_only_external_tier_matches():
    lib = _library_with()
    rows = [
        (_relation_stub("ext-1"), lib, "ext-1"),
        (_relation_stub("ext-1"), lib, "wrong-anchor"),
    ]
    report = measurement.compounding_accuracy(rows)
    assert report.external_scored_count == 2
    assert report.valid is True
    assert report.scored[0].correct is True
    assert report.scored[1].correct is False


def test_compounding_over_only_system_generated_matches_is_invalid():
    """The seeded regression this task fixes: once write-back is on, the
    nearest anchor is frequently the system's own prior SYSTEM_GENERATED
    output. A compounding report resting entirely on such rows must report
    valid=False, never publish a number."""
    lib = _library_with()
    rows = [
        (_relation_stub("sys-1"), lib, "sys-1"),
        (_relation_stub("sys-1"), lib, "sys-1"),
    ]
    report = measurement.compounding_accuracy(rows)
    assert report.external_scored_count == 0
    assert report.valid is False
    assert report.coverage == 0.0


def test_ranked_external_cousins_excludes_system_generated_even_when_nearest():
    """SYSTEM_GENERATED must not displace a real EXTERNAL anchor sitting
    just behind it in the neighbour set -- it is simply excluded, the
    EXTERNAL candidate further down the ranking is still found."""
    lib = _library_with()
    relation = SimpleNamespace(ranked_cousins=(("sys-1", 0.05), ("ext-1", 0.20)))
    external = measurement.ranked_external_cousins(relation, lib)
    assert external == (("ext-1", 0.20),)


def test_compounding_coverage_reflects_recovered_rows_not_zero():
    """Reproduces the M.3 defect being fixed: a raw-nearest-match scorer
    would report these rows unscored (coverage ~0) because the nearest
    match is SYSTEM_GENERATED; scoring against the nearest EXTERNAL cousin
    recovers them."""
    lib = _library_with()
    relation = SimpleNamespace(ranked_cousins=(("sys-1", 0.05), ("ext-1", 0.20)))
    rows = [(relation, lib, "ext-1") for _ in range(10)]
    report = measurement.compounding_accuracy(rows)
    assert report.coverage == 1.0
    assert report.valid is True


# ── C.3(b): uncertainty variance checked within a source ───────────────────


def test_variance_passes_across_batch_but_fails_within_one_source():
    """The seeded regression: reasons vary across sources (satisfying the
    old batch-only check) but are constant *within* one source -- this must
    now FAIL, even though it passed before this task."""
    relations = []
    for source in ("src-a", "src-b", "src-c", "src-d", "src-e"):
        boilerplate = (f"thin_anchor_coverage:{source}",)
        relations += [_relation_stub("x", reasons=boilerplate) for _ in range(4)]

    batch_only = degeneracy.check_uncertainty_variance(relations)
    assert batch_only.passes is True  # 5 distinct reason sets, no repeat > 0.8

    per_source = degeneracy.check_uncertainty_variance(
        relations,
        group_by=lambda r: r.uncertainty_reasons[0].split(":", 1)[1],
    )
    assert per_source.passes is False
    assert all(frac == 1.0 for frac in per_source.per_group_max_repeat_fraction.values())


def test_variance_passes_within_source_when_reasons_actually_vary():
    relations = []
    for source in ("src-a", "src-b"):
        for i in range(6):
            relations.append(
                _relation_stub("x", reasons=(f"divergence_axis:{source}", f"content:{i}"))
            )

    per_source = degeneracy.check_uncertainty_variance(
        relations,
        group_by=lambda r: r.uncertainty_reasons[0].split(":", 1)[1],
    )
    assert per_source.passes is True


# ── C.3(c): calibration binds to confidence, over-confidence blocks release ─


def test_seeded_overconfident_engine_is_caught_and_blocks_release():
    """A seeded engine that states high confidence but is realised wrong
    must be caught by the calibration report, and blocks_release must fire
    -- G.1's rule, fed CousinRelation.confidence rather than mass."""
    records = [calibration.ScoredRelation(confidence=0.95, correct=False) for _ in range(8)]
    records += [calibration.ScoredRelation(confidence=0.95, correct=True) for _ in range(2)]
    report = calibration.calibration_report(records)
    assert report.overconfident is True
    assert report.blocks_release is True


def test_well_calibrated_engine_does_not_block_release():
    records = [calibration.ScoredRelation(confidence=0.9, correct=True) for _ in range(9)]
    records += [calibration.ScoredRelation(confidence=0.9, correct=False) for _ in range(1)]
    report = calibration.calibration_report(records)
    assert report.blocks_release is False
