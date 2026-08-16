from __future__ import annotations

import json
from dataclasses import asdict

from portal.modules.security.core.bully import cousin_calibration_bench as bench
from portal.modules.security.core.bully import cousin_engine, evidence, signatures
from portal.modules.security.core.episode import Episode


class AxisSnapshot:
    def __init__(self, parent: dict, distractor: dict | None = None):
        self.parent = parent
        self.distractor = distractor
        self.queries: list[tuple[str, dict | None]] = []

    def knn(self, query, k, filters=None):
        self.queries.append((query, filters))
        if filters == {"family": self.parent["family"]}:
            return [(self.parent, 0.9)]
        if query.startswith("actions:") and self.distractor:
            return [(self.distractor, 0.01)]
        return []

    def stats(self):
        return {"row_count": 1 + bool(self.distractor)}


class EmptySnapshot:
    def knn(self, query, k, filters=None):
        return []

    def stats(self):
        return {"row_count": 0}


def test_semantic_query_is_behavioral_and_near_mutations_retain_shared_text():
    parent = bench.CALIB_PARENTS_V1[0]
    variants = bench.generate_variants(parent)
    left = signatures.build_signature(variants[0].episode_view, variants[0].telemetry_view)
    right = signatures.build_signature(variants[1].episode_view, variants[1].telemetry_view)

    left_query = signatures.semantic_query(left)
    right_query = signatures.semantic_query(right)
    assert left.canonical_fingerprint not in left_query
    assert right.canonical_fingerprint not in right_query
    assert left_query.startswith("actions:")
    assert {"T1558.003", "active-directory"} <= set(left_query.split())
    assert len(set(left_query.split()) & set(right_query.split())) >= 8


def test_family_axis_recovers_parent_when_semantic_axis_misses():
    parent = bench.CALIB_PARENTS_V1[0]
    parent_record = bench.parent_reference_record(parent)
    distractor = {
        **bench.parent_reference_record(bench.CALIB_PARENTS_V1[1]),
        "record_id": "semantic-distractor",
        "signature_id": "semantic-distractor",
    }
    snapshot = AxisSnapshot(parent_record, distractor)
    child = bench.generate_variants(parent)[0]

    result = bench.grade_blind(child, snapshot)
    assert result.reference_signature_id == parent.parent_id
    assert result.parent_present_in_candidates is True
    assert any(filters == {"family": parent.family} for _query, filters in snapshot.queries)


def test_parent_index_and_grade_signature_representations_are_symmetric():
    parent = bench.CALIB_PARENTS_V1[0]
    record = bench.parent_reference_record(parent)
    rebuilt = signatures.build_signature(
        {"episode_id": parent.parent_id, "target_host": parent.reference_scenario["target_host"]},
        {
            key: record[key]
            for key in (
                "action_sequence",
                "event_graph",
                "parameter_families",
                "context_topology",
                "artifacts",
                "attack_mappings",
                "telemetry_shape",
            )
        },
    )
    assert rebuilt.canonical_fingerprint == record["field_signature"]
    candidates = cousin_engine.candidate_set(rebuilt, semantic_candidates=[(record, 0.0)])
    assessment = cousin_engine.grade(
        rebuilt,
        candidates,
        cousin_engine.CoverageView(
            applicable_detection_ids=("control",), fired_detection_ids=("control",)
        ),
    )
    assert assessment.relationship == "SAME"


def test_production_episode_adapter_reads_real_shipped_telemetry(tmp_path):
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "mitre_technique": ["T1021.002"],
                "telemetry": {
                    "windows:security": [
                        {"EventCode": 4688, "Image": "wmic.exe", "CommandLine": "process call"}
                    ]
                },
            }
        )
    )
    episode = Episode(
        episode_id="ep-control",
        scenario="lateral-movement",
        target_host="host-1",
        started_at=0.0,
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_OBSERVED",
        detection_status="DETECTION_CONFIRMED",
        evidence_refs=[str(capture)],
    )

    view = evidence.adapt_episode_telemetry(episode)
    assert view["action_sequence"] == ["event-0:4688"]
    assert view["attack_mappings"] == [{"technique_id": "T1021.002"}]
    assert view["context_topology"]["family"] == "lateral-movement"
    assert view["detector_outcomes"] == {"episode:lateral-movement": "fired"}


def test_degenerate_instrument_is_invalid_and_emits_no_curve(tmp_path):
    report = bench.run_bench(EmptySnapshot(), tmp_path)
    assert report.status == "INVALID"
    assert report.controls["identity"]["passed"] is True
    assert report.controls["retrieval_health"]["passed"] is False
    assert report.curve == ()
    assert report.calibration_proposal is None
    assert (tmp_path / "calibration_report.json").exists()
    assert not (tmp_path / "calibration_curve.csv").exists()
    assert not (tmp_path / "calibration_curve.svg").exists()


def test_failed_controls_cannot_propose_thresholds():
    variant = bench.generate_variants(bench.CALIB_PARENTS_V1[0])[0]
    result = bench.BlindGrade(
        variant=variant,
        relationship="NEW",
        response="MISSED",
        distance=0.8,
        decomposition=asdict(cousin_engine.Decomposition(0.8, 0.8, 0.8, 0.8, 0.8)),
        confidence=1.0,
        reference_signature_id=None,
    )
    report = bench.score((result,), controls={"passed": False})
    assert report.status == "INVALID"
    assert report.curve == ()
    assert report.calibration_proposal is None


def test_response_oracle_records_detector_signal_independence():
    response, detail = bench._oracle_response(
        "TicketEncryptionType=0x17",
        ["T1558.003"],
        {"detector-opaque": "missed"},
    )
    assert response == "NEAR_MISS"
    assert detail["_independence_contract"]["independence_established"] is True
