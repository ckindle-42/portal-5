"""P6.8 cousin-calibration: independent x-axis, blind y-axis, no contamination."""

from __future__ import annotations

import inspect
import json
from dataclasses import asdict

from portal.modules.security.core.bully import cousin_calibration_bench as bench


class FakeReadOnlySnapshot:
    def __init__(self, records):
        self.records = records
        self.queries = []

    def knn(self, query, k, filters=None):
        self.queries.append({"query": query, "k": k, "filters": filters})
        return [(record, 0.08 + index * 0.01) for index, record in enumerate(self.records[:k])]

    def stats(self):
        return {"row_count": len(self.records)}


def test_frozen_parent_set_is_versioned_hashed_and_detection_covered():
    assert bench.CALIB_PARENT_SET_VERSION == "CALIB_PARENTS_V1"
    assert len(bench.CALIB_PARENTS_V1) == 4
    assert len(bench.CALIB_PARENTS_V1_SNAPSHOT_HASH) == 64
    assert all(parent.covering_detection_id for parent in bench.CALIB_PARENTS_V1)
    assert len({parent.family for parent in bench.CALIB_PARENTS_V1}) == 4


def test_construction_distance_is_deterministic_monotonic_and_grader_independent():
    parent = bench.CALIB_PARENTS_V1[0]
    variants = bench.generate_variants(parent)
    distances = [variant.d_applied for variant in variants]
    assert distances == sorted(distances)
    assert distances[0] > 0
    assert distances[-1] == 1.0
    assert bench.construction_distance(variants[3].plan) == variants[3].d_applied

    source = inspect.getsource(bench.construction_distance)
    assert "cousin_engine" not in source
    assert "weighted_composite" not in source
    assert "OPERATOR_CLASS_WEIGHTS" in source


def test_variant_generation_is_byte_identical_and_held_out():
    parent = bench.CALIB_PARENTS_V1[1]
    first = json.dumps([asdict(value) for value in bench.generate_variants(parent)], sort_keys=True)
    second = json.dumps(
        [asdict(value) for value in bench.generate_variants(parent)], sort_keys=True
    )
    assert first == second
    assert all(
        value.plan.replay_policy == "held_out_never_index"
        for value in bench.generate_variants(parent)
    )


def test_blind_grade_calls_real_path_without_parent_hint_or_snapshot_write():
    records = [bench.parent_reference_record(parent) for parent in bench.CALIB_PARENTS_V1]
    snapshot = FakeReadOnlySnapshot(records)
    child = bench.generate_variants(bench.CALIB_PARENTS_V1[0])[2]
    before = snapshot.stats()["row_count"]
    result = bench.grade_blind(child, snapshot)
    assert snapshot.stats()["row_count"] == before
    assert len(snapshot.queries) >= 4
    assert snapshot.queries[0]["query"] != child.parent_id
    assert len(snapshot.queries[0]["query"]) != 64
    assert snapshot.queries[0]["query"].startswith("actions:")
    assert any(query["filters"] == {"family": child.family} for query in snapshot.queries)
    assert result.relationship in {
        "SAME",
        "SIMILAR",
        "NEW",
        "DIFFERENT",
        "ANOMALOUS_UNCLASSIFIED",
    }
    assert set(result.decomposition) == {"behavior", "telemetry", "semantic", "attack", "context"}


def _grade(variant, *, relationship, distance, response="NEAR_MISS"):
    return bench.BlindGrade(
        variant=variant,
        relationship=relationship,
        response=response,
        distance=distance,
        decomposition={
            "behavior": distance,
            "telemetry": distance,
            "semantic": distance,
            "attack": distance,
            "context": distance,
        },
        confidence=1.0,
        reference_signature_id=variant.parent_id,
    )


def test_scoring_detects_three_primary_failure_classes_and_emits_proposal():
    variants = bench.generate_variants(bench.CALIB_PARENTS_V1[0])
    mid_new = _grade(variants[2], relationship="NEW", distance=0.2)
    overclaim = _grade(variants[3], relationship="SAME", distance=0.2)
    falling_a = _grade(variants[0], relationship="SIMILAR", distance=0.5)
    falling_b = _grade(variants[1], relationship="SIMILAR", distance=0.1)
    far_false_cousin = _grade(variants[-1], relationship="SIMILAR", distance=0.7)
    report = bench.score((mid_new, overclaim, falling_a, falling_b, far_false_cousin))
    assert report.passed is False
    assert report.failures["mid_band_graded_new"]
    assert report.failures["variant_graded_same"]
    assert report.failures["non_monotonic"]
    assert report.failures["false_cousin"]
    assert report.calibration_proposal["status"] == "operator_confirmation_required"
    assert report.calibration_proposal["proposed_thresholds"]


def test_response_axis_near_miss_comes_from_independent_discriminator_oracle():
    variant = next(
        value
        for value in bench.generate_variants(bench.CALIB_PARENTS_V1[0])
        if value.discriminator_evasion
    )
    row = bench.score((_grade(variant, relationship="SIMILAR", distance=0.2),)).curve[0]
    assert row["oracle_result"] == "ABSENT"
    assert row["oracle_response"] == "NEAR_MISS"


def test_run_bench_writes_curve_report_csv_and_plot_without_indexing_children(tmp_path):
    records = [bench.parent_reference_record(parent) for parent in bench.CALIB_PARENTS_V1]
    snapshot = FakeReadOnlySnapshot(records)
    before = snapshot.stats()["row_count"]
    report = bench.run_bench(snapshot, tmp_path)
    assert snapshot.stats()["row_count"] == before
    assert len(report.curve) == len(bench.CALIB_PARENTS_V1) * len(bench.FROZEN_SWEEP)
    assert (tmp_path / "calibration_report.json").exists()
    assert (tmp_path / "calibration_curve.csv").exists()
    assert (tmp_path / "calibration_curve.svg").exists()
    payload = json.loads((tmp_path / "calibration_report.json").read_text())
    assert payload["policy_version"] == "CALIB_DISTANCE_POLICY_V1"
    assert payload["controls"]["passed"] is True
