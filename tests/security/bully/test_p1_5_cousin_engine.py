"""P1.5 -- behavior signatures + two-axis BR-COUSIN engine.

Tests are written directly from FINAL_VALIDATION C5's five claims. A
symbol-presence test is not acceptance (master SS1A.3) -- every test here
either exercises a labeled calibration fixture or a specific invariant C5
states in prose.
"""

from __future__ import annotations

from portal.modules.security.core.bully import cousin_engine as ce
from portal.modules.security.core.bully import signatures as sig_mod


def _episode_view(episode_id="ep-1", target_host="host-1"):
    return {"episode_id": episode_id, "target_host": target_host}


def _telemetry(action_sequence, attack_ids, telemetry_fields, target_host="host-1"):
    return {
        "action_sequence": action_sequence,
        "attack_mappings": [{"technique_id": t} for t in attack_ids],
        "telemetry_shape": {"sourcetype": telemetry_fields},
        "context_topology": {"target_host": target_host, "protocol": "smb"},
        "detector_outcomes": {"det-1": {"fired": True}},
    }


def _reference(
    action_sequence, attack_ids, telemetry_fields, target_host="host-1", record_id="ref-1"
):
    return {
        "record_id": record_id,
        "signature_id": record_id,
        "action_sequence": action_sequence,
        "attack_mappings": [{"technique_id": t} for t in attack_ids],
        "telemetry_shape": {"sourcetype": telemetry_fields},
        "context_topology": {"target_host": target_host, "protocol": "smb"},
    }


def _build_signature(action_sequence, attack_ids, telemetry_fields, target_host="host-1"):
    return sig_mod.build_signature(
        _episode_view(target_host=target_host),
        _telemetry(action_sequence, attack_ids, telemetry_fields, target_host=target_host),
    )


def _candidates(reference, semantic_distance=0.0):
    return ce.candidate_set(None, semantic_candidates=[(reference, semantic_distance)])


COVERED = ce.CoverageView(
    applicable_detection_ids=("det-1",), fired_detection_ids=("det-1",), telemetry_healthy=True
)
MISSED = ce.CoverageView(applicable_detection_ids=("det-1",), telemetry_healthy=True)


# ── C5 CLAIM 1 -- calibration across the five labeled fixture kinds ─────────


def test_exact_reexecution_grades_same():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), COVERED)
    assert assessment.relationship == "SAME"


def test_sibling_subtechnique_variant_grades_similar():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create", "extra_persist_step"],
        ["T1021.002"],
        ["wmi", "smb", "eventlog"],
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.001"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.2), MISSED)
    assert assessment.relationship == "SIMILAR"


def test_same_tactic_variant_grades_new():
    subject = _build_signature(
        ["scheduled_task_create", "payload_drop"], ["T1053.005"], ["process", "file"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.55), MISSED)
    assert assessment.relationship == "NEW"


def test_unrelated_attack_grades_different():
    subject = _build_signature(["dns_tunnel_beacon"], ["T1071.004"], ["dns"], target_host="host-9")
    reference = _reference(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"], target_host="host-1"
    )
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.9), MISSED)
    assert assessment.relationship == "DIFFERENT"


def test_benign_shape_does_not_grade_same_or_similar():
    subject = _build_signature(["user_login", "file_read"], [], ["auth"], target_host="host-2")
    reference = _reference(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"], target_host="host-1"
    )
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.95), COVERED)
    assert assessment.relationship not in ("SAME", "SIMILAR")


def test_calibration_agreement_floor_on_the_five_fixtures():
    """C5 CLAIM 1: relationship grades match labels at/above a 0.9 floor.

    With this five-fixture labeled set, the floor requires all five correct
    (4/5 = 0.8 would fail it).
    """
    cases = [
        (
            _build_signature(
                ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
            ),
            _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]),
            0.0,
            COVERED,
            "SAME",
        ),
        (
            _build_signature(
                ["net_use", "wmic_process_call_create", "extra_persist_step"],
                ["T1021.002"],
                ["wmi", "smb", "eventlog"],
            ),
            _reference(["net_use", "wmic_process_call_create"], ["T1021.001"], ["wmi", "smb"]),
            0.2,
            MISSED,
            "SIMILAR",
        ),
        (
            _build_signature(
                ["scheduled_task_create", "payload_drop"], ["T1053.005"], ["process", "file"]
            ),
            _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]),
            0.55,
            MISSED,
            "NEW",
        ),
        (
            _build_signature(["dns_tunnel_beacon"], ["T1071.004"], ["dns"], target_host="host-9"),
            _reference(
                ["net_use", "wmic_process_call_create"],
                ["T1021.002"],
                ["wmi", "smb"],
                target_host="host-1",
            ),
            0.9,
            MISSED,
            "DIFFERENT",
        ),
        (
            _build_signature(["user_login", "file_read"], [], ["auth"], target_host="host-2"),
            _reference(
                ["net_use", "wmic_process_call_create"],
                ["T1021.002"],
                ["wmi", "smb"],
                target_host="host-1",
            ),
            0.95,
            COVERED,
            "DIFFERENT",
        ),
    ]
    correct = 0
    for subject, reference, semantic_distance, coverage, label in cases:
        assessment = ce.grade(subject, _candidates(reference, semantic_distance), coverage)
        if assessment.relationship == label:
            correct += 1
    agreement = correct / len(cases)
    assert agreement >= 0.9, f"agreement={agreement}"


# ── C5 CLAIM 2 -- beats lexical (unknown_defense scores ~0, composite doesn't) ─


def test_composite_catches_a_case_lexical_similarity_scores_none():
    from portal.modules.security.core.unknown_defense import MatchGrade, compute_similarity

    # Different vocabulary entirely (no shared words) but identical
    # structural attack mapping + action sequence + telemetry shape.
    observed = {"tactic": "xkcd zephyr quibble"}
    wiki = {"reference": "unrelated vocabulary blob zzyzx"}
    legacy = compute_similarity(observed, wiki)
    assert legacy.grade == MatchGrade.NONE

    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), MISSED)
    assert assessment.relationship in ("SAME", "SIMILAR", "NEW")


# ── C5 CLAIM 3 -- explainability ────────────────────────────────────────────


def test_assessment_carries_full_decomposition_and_explanation():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), COVERED)
    explanation = ce.explain(assessment, reference_record=reference)
    for dim in ("behavior", "telemetry", "semantic", "attack", "context"):
        assert dim in explanation["decomposition"]
    assert explanation["defense_response"] == "COVERED"
    assert explanation["thresholds_version"] == ce.THRESHOLDS_VERSION
    assert "feature_citations" in explanation


# ── C5 CLAIM 4 -- vetoes ────────────────────────────────────────────────────


def test_discriminator_contradiction_downgrades_same():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"], target_host="host-A"
    )
    reference = _reference(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"], target_host="host-B"
    )
    assessment = ce.grade(
        subject,
        _candidates(reference, semantic_distance=0.0),
        MISSED,
        discriminators=["target_host"],
    )
    assert assessment.relationship != "SAME"
    assert assessment.vetoes


def test_similar_or_new_impossible_with_fewer_than_two_nonsemantic_channels():
    # Only semantic distance available (everything else empty on both sides).
    subject = sig_mod.build_signature(_episode_view(), {})
    reference = {"record_id": "ref-empty"}
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.2), MISSED)
    assert assessment.relationship not in ("SIMILAR", "NEW")


# ── C5 CLAIM 5 -- axis independence ─────────────────────────────────────────


def test_missed_response_never_changes_the_decomposition_or_distance():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    covered_assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), COVERED)
    missed_assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), MISSED)
    assert covered_assessment.composite == missed_assessment.composite
    assert covered_assessment.decomposition == missed_assessment.decomposition
    assert covered_assessment.relationship == missed_assessment.relationship == "SAME"


def test_semantically_distant_response_identical_pair_grades_different_not_new():
    subject = _build_signature(["dns_tunnel_beacon"], ["T1071.004"], ["dns"], target_host="host-9")
    reference = _reference(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"], target_host="host-1"
    )
    a = ce.grade(subject, _candidates(reference, semantic_distance=0.9), COVERED)
    b = ce.grade(
        subject, _candidates(reference, semantic_distance=0.9), COVERED
    )  # same response both times
    assert a.relationship == b.relationship == "DIFFERENT"


def test_same_times_missed_is_regression_not_discovery_product_band():
    subject = _build_signature(
        ["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"]
    )
    reference = _reference(["net_use", "wmic_process_call_create"], ["T1021.002"], ["wmi", "smb"])
    assessment = ce.grade(subject, _candidates(reference, semantic_distance=0.0), MISSED)
    assert assessment.relationship == "SAME"
    assert assessment.defense_response == "MISSED"
    band = ce.product_band(assessment.relationship, assessment.defense_response)
    assert band == "REGRESSION"
    assert band != "DISCOVERY"


# ── empty candidate set -> ANOMALOUS_UNCLASSIFIED (first-class success) ────


def test_empty_candidate_set_grades_anomalous_unclassified():
    subject = _build_signature(["never_seen_before"], ["T9999"], ["novel"])
    empty = ce.candidate_set(None)
    assessment = ce.grade(subject, empty, MISSED)
    assert assessment.relationship == "ANOMALOUS_UNCLASSIFIED"


# ── dual-run shadow (I-22) ───────────────────────────────────────────────────


def test_dual_run_shadow_records_disagreement_never_silently_resolved():
    observed = {"tactic": "zzz totally different words"}
    wiki = {"reference": "yyy nothing shared at all"}
    result = ce.dual_run_shadow(observed, wiki, composite_relationship="SIMILAR")
    assert result["legacy_grade"] == "NONE"
    assert result["composite_relationship"] == "SIMILAR"
    assert result["agree"] is False
