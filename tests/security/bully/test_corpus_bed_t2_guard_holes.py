"""T.2 -- close the three guard holes C.6 exposed in its own output
(TASK_BULLY_REAL_TELEMETRY_V1). Each of C.6's three shapes fails for its
own reason; omitting a required scale input is a TypeError, not a silent
pass."""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import corpus_bed

_C6_RECORDS_AVAILABLE = {
    "portal5_lab": 19_300_000,
    "botsv1": 33_400_000,
    "botsv2": 226_300_000,
    "botsv3": 2_000_000,
}


# ── hole 1: records_read == 0 must hard-fail is_haystack, unconditionally ──


def test_zero_records_read_is_never_a_haystack_even_on_a_huge_corpus():
    """The exact C.6 shape: 281M records available, is_haystack must not
    read True just because `records_read and total and ...` short-circuits
    on the falsy zero."""
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE, records_read=0, units_fitted=4183, units_scored=200
    )
    assert bed.is_haystack is False
    assert any("no_records_read" in r for r in bed.reasons)


def test_no_records_read_reason_checked_before_partial_read_branch():
    # records_read=0 must not ALSO produce a misleading partial_read reason
    # (0/total would read as "0% captured", true but not the real defect).
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE, records_read=0, units_fitted=4183, units_scored=200
    )
    assert not any(r.startswith("partial_read") for r in bed.reasons)


def test_nonzero_partial_read_still_reported_as_before():
    bed = corpus_bed.assess_bed(
        {"portal5_lab": 50_000, "botsv1": 50_000, "botsv2": 50_000, "botsv3": 50_000},
        records_read=10_000,
        units_fitted=4183,
        units_scored=200,
    )
    assert any(r.startswith("partial_read") for r in bed.reasons)


# ── hole 2: the scale floors are wired and required, not optional ──────────


def test_min_scored_units_and_fit_ratio_constants_exist():
    assert corpus_bed.MIN_SCORED_UNITS == 10_000
    assert corpus_bed.MIN_FIT_TO_SCORE_RATIO == 2.0


def test_c6_scale_scored_200_against_10000_floor_fails():
    """C.6's exact shape: 200 scored, 4183 fitted -- fails the scored-units
    floor (a fit/score ratio of ~21x clears MIN_FIT_TO_SCORE_RATIO on its
    own, so this reason must fire independently)."""
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE, records_read=19_999, units_fitted=4183, units_scored=200
    )
    assert any("scored_sample_too_small" in r for r in bed.reasons)


def test_fit_to_score_ratio_too_small_when_fit_not_wide_enough():
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE,
        records_read=19_999,
        units_fitted=15_000,
        units_scored=10_000,
    )
    assert any("fit_to_score_ratio_too_small" in r for r in bed.reasons)


def test_proper_long_run_scale_passes_scale_floors_clean():
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE,
        records_read=200_000_000,
        units_fitted=180_000,
        units_scored=25_000,
    )
    assert bed.is_haystack is True
    assert not any("scored_sample_too_small" in r for r in bed.reasons)
    assert not any("fit_to_score_ratio_too_small" in r for r in bed.reasons)


def test_units_fitted_and_units_scored_are_required_keyword_arguments():
    with pytest.raises(TypeError):
        corpus_bed.assess_bed(_C6_RECORDS_AVAILABLE, records_read=100)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        corpus_bed.assess_bed(_C6_RECORDS_AVAILABLE, records_read=100, units_fitted=10)  # type: ignore[call-arg]


# ── hole 3: zero floor recall FAILs acceptance ──────────────────────────────


def test_c6_exact_numbers_bed_acceptance_is_invalid_with_all_three_reasons():
    """Validated against C.6's exact numbers: records_read=0, 4 answer-key
    techniques all missed, background FP 0.911."""
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE, records_read=0, units_fitted=4183, units_scored=200
    )
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=0,
        answer_key_total=4,
        cousin_hit=8,
        cousin_total=20,
        background_flagged=911,
        background_total=1000,
        bed=bed,
    )
    assert acceptance.verdict == "INVALID"
    reasons = " ".join(acceptance.reasons)
    assert "no_records_read" in reasons
    assert "zero_floor_recall: 0/4" in reasons
    assert "background_fp_rate_0.911>0.1" in reasons


def test_zero_floor_recall_fails_even_on_an_otherwise_valid_haystack():
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE,
        records_read=200_000_000,
        units_fitted=180_000,
        units_scored=25_000,
    )
    assert bed.is_haystack is True
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=0,
        answer_key_total=4,
        cousin_hit=10,
        cousin_total=20,
        background_flagged=10,
        background_total=1000,
        bed=bed,
    )
    assert acceptance.verdict == "FAIL"
    assert any("zero_floor_recall: 0/4" in r for r in acceptance.reasons)


def test_nonzero_floor_recall_does_not_trigger_the_zero_floor_reason():
    bed = corpus_bed.assess_bed(
        _C6_RECORDS_AVAILABLE,
        records_read=200_000_000,
        units_fitted=180_000,
        units_scored=25_000,
    )
    acceptance = corpus_bed.bed_acceptance(
        answer_key_hit=1,
        answer_key_total=4,
        cousin_hit=10,
        cousin_total=20,
        background_flagged=10,
        background_total=1000,
        bed=bed,
    )
    assert not any("zero_floor_recall" in r for r in acceptance.reasons)
