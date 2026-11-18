"""The calibrated funnel on production-shaped windows."""

from __future__ import annotations

from portal.modules.security.core.review import calibration as cal
from portal.modules.security.core.review import funnel, intake

from ._fakes import three_source_window

LEVELS = ("L2_ENTITY",)
POLICY = funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=LEVELS)


# ── funnel ────────────────────────────────────────────────────────────────────


def test_uncalibrated_channels_raise_nothing_and_say_so() -> None:
    scores = [funnel.UnitScores("u1", "L2_ENTITY", unusual=0.99, similar=0.99)]
    (decision,) = funnel.decide(scores, cal.CalibrationSet(), POLICY)
    assert not decision.flagged
    assert set(decision.uncalibrated) == {funnel.CHANNEL_UNUSUAL, funnel.CHANNEL_SIMILAR}


def test_decide_flags_above_threshold_and_ranks_by_calibrated_p() -> None:
    cset = cal.CalibrationSet()
    cset.put(
        cal.fit_calibration("unusual", "L2_ENTITY", [i / 100 for i in range(100)], 0.1, basis="b")
    )
    scores = [
        funnel.UnitScores("low", "L2_ENTITY", unusual=0.50, similar=None),
        funnel.UnitScores("high", "L2_ENTITY", unusual=0.99, similar=None),
        funnel.UnitScores("mid", "L2_ENTITY", unusual=0.93, similar=None),
        funnel.UnitScores("chain", "L3_CHAIN", unusual=0.99, similar=None),  # level not enabled
    ]
    ranked = funnel.rank(funnel.decide(scores, cset, POLICY))
    assert [d.unit_id for d in ranked] == ["high", "mid", "low"]
    assert [d.flagged for d in ranked] == [True, True, False]


def test_split_is_deterministic_and_disjoint() -> None:
    result = intake.build_window_units(three_source_window(seed=1, n=200))
    units = [u.unit for u in result.units]
    fit_a, cal_a = funnel.split_units(units, salt="x")
    fit_b, cal_b = funnel.split_units(units, salt="x")
    assert [u.unit_id for u in fit_a] == [u.unit_id for u in fit_b]
    assert not {u.unit_id for u in fit_a} & {u.unit_id for u in cal_a}
    assert len(fit_a) + len(cal_a) == len(units)


def test_baseline_survives_a_roundtrip() -> None:
    result = intake.build_window_units(three_source_window(seed=2, n=200))
    units = [u.unit for u in result.units]
    model = funnel.fit_baseline(units, "env")
    again = funnel.baseline_from_dict(funnel.baseline_to_dict(model))
    probe = [u for u in units if u.level == "L2_ENTITY"][:5]
    assert [funnel.unusual_score(u, model) for u in probe] == [
        funnel.unusual_score(u, again) for u in probe
    ]
