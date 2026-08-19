"""G.1 -- confidence calibration + downstream honouring: a seeded
over-confident engine is caught; an escalation below threshold without
evidence is rejected; calibration is recomputed per run, never hand-set."""

from __future__ import annotations

from portal.modules.security.core.bully import calibration


def test_seeded_overconfident_engine_is_caught_and_blocks_release():
    # Stated confidence ~0.95 but only 40% realised accuracy in that bin.
    records = [calibration.ScoredRelation(confidence=0.95, correct=i < 4) for i in range(10)]
    report = calibration.calibration_report(records)
    assert report.overconfident is True
    assert report.blocks_release is True


def test_well_calibrated_engine_is_not_flagged():
    # mean stated confidence matches realised accuracy in every populated bin.
    records = [calibration.ScoredRelation(confidence=0.95, correct=i < 9) for i in range(10)]
    records += [calibration.ScoredRelation(confidence=0.15, correct=i < 2) for i in range(10)]
    report = calibration.calibration_report(records)
    assert report.overconfident is False
    assert report.blocks_release is False
    assert report.brier_score is not None


def test_escalation_below_threshold_without_evidence_is_rejected():
    decision = calibration.gate_escalation(0.4, has_independent_evidence=False)
    assert decision.allowed is False
    assert len(decision.reasons) == 2


def test_escalation_requires_both_threshold_and_evidence():
    high_conf_no_evidence = calibration.gate_escalation(0.9, has_independent_evidence=False)
    assert high_conf_no_evidence.allowed is False

    evidence_low_conf = calibration.gate_escalation(0.3, has_independent_evidence=True)
    assert evidence_low_conf.allowed is False

    both = calibration.gate_escalation(0.9, has_independent_evidence=True)
    assert both.allowed is True
    assert both.reasons == ()


def test_calibration_is_recomputed_per_run_not_hand_set():
    records_a = [calibration.ScoredRelation(confidence=0.5, correct=True) for _ in range(5)]
    records_b = [calibration.ScoredRelation(confidence=0.5, correct=False) for _ in range(5)]
    report_a = calibration.calibration_report(records_a)
    report_b = calibration.calibration_report(records_b)
    assert report_a.overconfident != report_b.overconfident
    matching_bin_a = next(b for b in report_a.bins if b.count)
    matching_bin_b = next(b for b in report_b.bins if b.count)
    assert matching_bin_a.realised_accuracy != matching_bin_b.realised_accuracy


def test_empty_records_report_no_scored_rows_without_error():
    report = calibration.calibration_report([])
    assert report.scored_count == 0
    assert report.brier_score is None
    assert report.overconfident is False
