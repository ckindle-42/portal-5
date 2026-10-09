"""The registered arms preserve the installed review defaults and legacy call defaults."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from portal.modules.security.core.bully import artifact_graph, discovery
from portal.modules.security.core.review.funnel import FunnelPolicy
from portal.modules.security.core.review.service import DEFAULT_READER
from portal.modules.security.core.review_eval import legacy_arm
from portal.modules.security.core.review_eval.arms import (
    ARMS,
    DEFAULT_READER_ARM,
    REVIEW_D0_CONFIG,
    get_arm,
)


def test_registered_arm_set_and_review_d0_configuration_are_frozen() -> None:
    assert set(ARMS) == {"legacy_funnel", "review_d0", "no_reader"}
    assert DEFAULT_READER_ARM == "no_reader"
    assert DEFAULT_READER is None
    assert get_arm("legacy_funnel").legacy
    assert not get_arm("review_d0").legacy
    assert get_arm(DEFAULT_READER_ARM).config is REVIEW_D0_CONFIG
    review_arm = get_arm("review_d0")
    assert review_arm.config is REVIEW_D0_CONFIG
    assert review_arm.config is not None
    assert review_arm.config.policy == FunnelPolicy(
        alpha_unusual=0.2,
        alpha_similar=0.2,
        levels=("L2_ENTITY", "L3_CHAIN"),
    )
    assert review_arm.config.suppress_benign == "exact_only"
    assert review_arm.config.top_k_anchors == 3
    assert review_arm.config.judge_max is None


def test_legacy_adapter_calls_shipped_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    enum_units = Mock(wraps=artifact_graph.enumerate_units)
    discover = Mock(wraps=discovery.discover)
    monkeypatch.setattr(artifact_graph, "enumerate_units", enum_units)
    monkeypatch.setattr(discovery, "discover", discover)
    result = legacy_arm.run_legacy_funnel({"botsv1:stream:http": []}, environment_id="legacy-smoke")

    assert enum_units.call_count == 1
    assert len(enum_units.call_args.args) == 1 and not enum_units.call_args.kwargs
    assert discover.call_count == 1
    assert len(discover.call_args.args) == 2 and not discover.call_args.kwargs
    assert result.fingerprint["legacy_unit_cap"] == str(artifact_graph.MAX_UNITS_PER_LEVEL)
    assert result.receipts[-1].name == "legacy.output"
