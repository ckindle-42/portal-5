from __future__ import annotations

import pytest


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
