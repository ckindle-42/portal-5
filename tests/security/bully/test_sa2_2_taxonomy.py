from __future__ import annotations

from portal.modules.security.core.bully.discovery_bench import discovery_band


def test_taxonomy_assignment_on_fixtures():
    assert discovery_band("SAME", "MISSED") == "REGRESSION"
    assert discovery_band("SAME", "NEAR_MISS") == "REGRESSION"
    assert discovery_band("SIMILAR", "MISSED") == "DISCOVERY"
    assert discovery_band("SIMILAR", "NEAR_MISS") == "DISCOVERY"
    assert discovery_band("NEW", "MISSED") == "DISCOVERY"
    assert discovery_band("NEW", "NEAR_MISS") == "DISCOVERY"
    assert discovery_band("ANOMALOUS_UNCLASSIFIED", "MISSED") == "DISCOVERY"
    assert discovery_band("ANOMALOUS_UNCLASSIFIED", "NEAR_MISS") == "DISCOVERY"
    assert discovery_band("DIFFERENT", "MISSED") == "NO-RELATION"
    assert discovery_band("SAME", "COVERED") == "FLOOR"
    assert discovery_band("SIMILAR", "COVERED") == "FLOOR"
    assert discovery_band("NEW", "INDETERMINATE") == "INDETERMINATE"


def test_same_x_missed_lands_as_regression_not_discovery():
    assert discovery_band("SAME", "MISSED") != "DISCOVERY"
    assert discovery_band("SAME", "MISSED") == "REGRESSION"


def test_anomalous_never_scored_as_a_miss():
    """A5: ANOMALOUS_UNCLASSIFIED x (MISSED|NEAR_MISS) must be DISCOVERY --
    never REGRESSION, NO-RELATION, or a bare failure classification."""
    for response in ("MISSED", "NEAR_MISS"):
        band = discovery_band("ANOMALOUS_UNCLASSIFIED", response)
        assert band == "DISCOVERY"
        assert band not in {"REGRESSION", "NO-RELATION"}
