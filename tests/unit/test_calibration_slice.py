from __future__ import annotations

import math

import pytest


def test_observed_36_record_slice_resolution_is_one_over_12() -> None:
    calibration_half_units = 11
    p_step = 1 / (calibration_half_units + 1)

    assert p_step == pytest.approx(0.0833, abs=0.0001)


def test_target_600_gives_120_resolution_steps_below_alpha_02() -> None:
    calibration_half_units = 600
    p_step = 1 / (calibration_half_units + 1)

    assert p_step < 0.002
    assert math.floor(0.2 / p_step) == 120


def test_slice_provenance_is_ignored_by_intake() -> None:
    from portal.modules.security.core.review import intake

    result = intake.build_window_units(
        {"portal5_lab:windows:security": [], "_provenance": {"p_step": 1 / 601}}
    )

    assert result.units == []
    assert result.events == {}


def test_build_reference_refuses_self_window_basis() -> None:
    from portal.modules.security.core.review import funnel, intake, pipeline
    from tests.security.review._fakes import three_source_window

    benign = intake.build_window_units(three_source_window(seed=40, n=10))
    policy = funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L2_ENTITY",))
    with pytest.raises(ValueError, match="refused basis='self_window'"):
        pipeline.build_reference(
            benign,
            policy=policy,
            index=None,
            embedder=None,
            environment_id="t",
            basis="self_window",
        )


def test_build_reference_keeps_benign_slice_basis() -> None:
    from portal.modules.security.core.review import funnel, intake, pipeline
    from tests.security.review._fakes import three_source_window

    benign = intake.build_window_units(three_source_window(seed=40, n=334))
    policy = funnel.FunnelPolicy(alpha_unusual=0.2, alpha_similar=0.2, levels=("L2_ENTITY",))
    reference = pipeline.build_reference(
        benign, policy=policy, index=None, embedder=None, environment_id="t"
    )

    assert reference.basis == "benign_slice"
    assert reference.calibration_window is benign
