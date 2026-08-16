from __future__ import annotations

from portal.modules.security.core.bully import discovery_bench
from portal.modules.security.core.bully.discovery_bench import discovery_band
from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot


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


def test_end_to_end_joint_scoring_on_fixture_corpus():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    bands = {v.specimen_id: v.discovery_band for v in verdicts}
    # sysmon-unrelated: probe's own response is COVERED -> FLOOR always,
    # regardless of the relationship to its nearest neighbor.
    assert bands["sysmon-unrelated"] == "FLOOR"
    # sysmon-kerberoast: MISSED response, and by fixture construction its
    # nearest real structural cousin is the cross-class Okta specimen, which
    # independently shares T1558.003 -> a real, truth-confirmed discovery.
    missed_verdict = next(v for v in verdicts if v.specimen_id == "sysmon-kerberoast")
    assert missed_verdict.discovery_band == "DISCOVERY"
    assert missed_verdict.truth_related is True
    assert missed_verdict.reference_signature_id == "okta-kerberoast-cousin"
