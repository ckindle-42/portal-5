"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.5): close the bed guard.

I.6 published `is_haystack: true` alongside ZERO scored units
(`scored_sample_too_small: 0<10000` was only a reason, never checked).
`scored_sample_too_small` must now force `is_haystack=False`, and every run
publishing recovery figures must publish `bed_acceptance` alongside them.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import corpus_bed as cb

# I.6's actual bed_report shape.
_I6_RECORDS_AVAILABLE = {"botsv3": 2_030_370}
_I6_RECORDS_READ = 213_311


def test_i6_bed_shape_now_returns_is_haystack_false():
    bed = cb.assess_bed(
        _I6_RECORDS_AVAILABLE,
        records_read=_I6_RECORDS_READ,
        units_fitted=0,
        units_scored=0,
    )
    assert bed.is_haystack is False
    assert any(r.startswith("scored_sample_too_small") for r in bed.reasons)


def test_zero_scored_units_forces_false_even_with_a_huge_corpus():
    bed = cb.assess_bed(
        {"botsv1": 30_000_000, "botsv2": 40_000_000, "botsv3": 2_000_000},
        records_read=50_000_000,
        units_fitted=0,
        units_scored=0,
    )
    assert bed.is_haystack is False


def test_enough_scored_units_can_pass():
    bed = cb.assess_bed(
        _I6_RECORDS_AVAILABLE,
        records_read=_I6_RECORDS_READ,
        units_fitted=cb.MIN_SCORED_UNITS * 3,
        units_scored=cb.MIN_SCORED_UNITS,
    )
    assert bed.is_haystack is True


def test_run_omitting_bed_acceptance_fails_validation():
    run_output = {
        "reach_report": {"reach_recall": 0.5},
        "inference_report": {"cross_schema_fraction": 0.3},
    }
    with pytest.raises(cb.RunOutputMissingBedAcceptanceError):
        cb.require_bed_acceptance(run_output)


def test_run_with_bed_acceptance_none_fails_validation():
    run_output = {"reach_report": {}, "bed_acceptance": None}
    with pytest.raises(cb.RunOutputMissingBedAcceptanceError):
        cb.require_bed_acceptance(run_output)


def test_run_publishing_bed_acceptance_passes_validation():
    run_output = {
        "reach_report": {"reach_recall": 0.5},
        "bed_acceptance": {"verdict": "PASS", "floor_known_recall": 0.5},
    }
    cb.require_bed_acceptance(run_output)  # must not raise
