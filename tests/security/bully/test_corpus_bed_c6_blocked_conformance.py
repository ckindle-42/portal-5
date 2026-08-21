"""C.6 -- a BLOCKED/INVALID corpus-bed run must not FAIL scoreboard
conformance for lacking a scoreboard/correctness-axis it never had the
chance to publish (TASK_BULLY_CORPUS_BED_V1 C.1: a run below the haystack
floor publishes INVALID and stops there)."""

from __future__ import annotations

from portal.modules.security.core.bully.scoreboard_conformance import check_run


def test_invalid_run_with_no_scoreboard_does_not_fail_conformance():
    run_json = {
        "plane": "INVALID",
        "reason": "not_a_haystack",
        "bed_report": {"is_haystack": False, "reasons": ["corpus_too_small:0<100000"]},
    }
    findings = check_run(run_json)
    assert not any(f.severity == "FAIL" for f in findings)


def test_blocked_run_with_no_scoreboard_does_not_fail_conformance():
    run_json = {"plane": "BLOCKED", "reason": "baseline_undersized"}
    findings = check_run(run_json)
    assert not any(f.severity == "FAIL" for f in findings)


def test_blocked_run_publishing_a_fabricated_headline_still_fails():
    """The BLOCKED-plane exemption skips the "must publish" checks, never
    the "must not fabricate" ones."""
    run_json = {
        "plane": "BLOCKED",
        "reason": "baseline_undersized",
        "scoreboard": {"invented_discovery_rate": 1.0},
    }
    findings = check_run(run_json)
    assert any(f.code == "invented_headline_metric" for f in findings)


def test_bed_acceptance_floor_zero_beside_selection_recall_one_is_not_a_contradiction():
    """Floor recall and selection recall measure different things by design
    (C3/Y.3) -- a live corpus-bed run legitimately reports one at 0.0 and
    the other at 1.0 in the same file; that must not FAIL conformance."""
    run_json = {
        "plane": "live",
        "per_row": [
            {
                "entity_id": "e1",
                "trust_class": "x",
                "trust_rank": 1,
                "false_flag": False,
                "known_benign": False,
                "candidate_state": "PENDING",
            }
        ],
        "correctness_axis_provenance": {"known_benign_rows_total": 0},
        "bed_acceptance": {"floor_known_recall": 0.0, "product_cousin_recall": 0.35},
        "selection_report": {"selection_recall": 1.0},
    }
    findings = check_run(run_json)
    assert not any(f.code == "recall_contradiction" for f in findings)


def test_genuine_same_concept_recall_contradiction_still_fails():
    """The guard still catches a run reporting its OWN detection recall as
    both 1.0 and 0.0 outside the orthogonal bed_acceptance/selection_report
    namespaces."""
    run_json = {
        "plane": "live",
        "per_row": [
            {
                "entity_id": "e1",
                "trust_class": "x",
                "trust_rank": 1,
                "false_flag": False,
                "known_benign": False,
                "candidate_state": "PENDING",
            }
        ],
        "correctness_axis_provenance": {"known_benign_rows_total": 0},
        "headline_recall": 1.0,
        "detection": {"recall": 0.0},
    }
    findings = check_run(run_json)
    assert any(f.code == "recall_contradiction" for f in findings)


def test_live_run_still_requires_the_correctness_axis():
    """The exemption is plane-scoped -- a live run with no correctness axis
    still FAILs, unchanged from before this fix."""
    run_json = {"plane": "live", "per_row": [{"entity_id": "e1"}]}
    findings = check_run(run_json)
    assert any(f.code == "correctness_axis_not_published" for f in findings)
