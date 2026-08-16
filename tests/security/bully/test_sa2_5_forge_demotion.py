from __future__ import annotations

from portal.modules.security.core.bully.cousin_calibration_bench import (
    CONSTRUCTION_CEILING_NOTE,
    per_rung_band_accuracy,
)


def _row(d_applied: float, correct: bool) -> dict:
    return {"d_applied": d_applied, "band_crossing_correct": correct}


def test_per_rung_breakdown_groups_by_construction_distance():
    rows = [
        _row(0.0, True),
        _row(0.0, True),
        _row(0.04, True),
        _row(0.04, False),
        _row(0.08, True),
    ]
    report = per_rung_band_accuracy(rows)
    rungs = {r["d_applied"]: r for r in report["rungs"]}
    assert rungs[0.0]["rows"] == 2
    assert rungs[0.0]["band_accuracy"] == 1.0
    assert rungs[0.04]["rows"] == 2
    assert rungs[0.04]["band_accuracy"] == 0.5
    assert rungs[0.08]["rows"] == 1


def test_construction_ceiling_note_is_stated_inline():
    report = per_rung_band_accuracy([_row(0.0, True)])
    assert report["construction_ceiling_note"] == CONSTRUCTION_CEILING_NOTE
    assert "not the product metric" in report["instrument_role"]
    assert "5/9" in CONSTRUCTION_CEILING_NOTE


def test_characterize_baseline_reports_per_rung_not_only_headline():
    from portal.modules.security.core.bully.cousin_calibration_bench import (
        _characterize_baseline,
    )

    rows = [
        {
            "d_applied": 0.0,
            "measurement_valid": True,
            "relationship": "SAME",
            "band_crossing_correct": True,
            "parent_id": "p1",
            "family_parent_correct": True,
            "candidate_set_size": 1,
            "true_parent_present_in_candidates": True,
            "family_parent_present_in_candidates": True,
            "grader_response": "COVERED",
            "oracle_response": "COVERED",
            "source_lane": "attack_data",
            "graded_distance": 0.0,
        }
    ]
    characterization = _characterize_baseline(rows, {"non_monotonic": [], "wrong_parent": []})
    assert "per_rung" in characterization
    assert characterization["per_rung"]["rungs"]
    assert characterization["band_crossing"]["headline_note"]
