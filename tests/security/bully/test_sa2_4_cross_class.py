from __future__ import annotations

from portal.modules.security.core.bully import discovery_bench
from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot


def test_cross_class_cohort_is_non_empty_and_separately_reported():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    breakout = discovery_bench.characterize_cross_class(verdicts, probes)
    assert breakout["cross_class"]["rows"] > 0
    assert breakout["same_class"]["rows"] > 0
    assert breakout["cross_class"]["rows"] + breakout["same_class"]["rows"] == len(verdicts)


def test_at_least_one_real_cross_class_discovery_is_characterized_end_to_end():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    breakout = discovery_bench.characterize_cross_class(verdicts, probes)
    discoveries = breakout["cross_class_discoveries"]
    assert len(discoveries) >= 1
    finding = next(d for d in discoveries if d["specimen_id"] == "sysmon-kerberoast")
    assert finding["reference_source_class"] == "OktaIM2:log"
    assert finding["truth_related"] is True
    assert "T1558.003" in finding["shared_technique_ids"]


def test_coverage_asymmetry_is_computed_from_real_per_class_detection_coverage():
    corpus = build_corpus()
    probes = discovery_bench.real_probe_specimens(corpus)
    findings = discovery_bench._coverage_asymmetry(probes)
    t1078 = next(f for f in findings if f["technique_id"] == "T1078")
    assert t1078["covered_in"] == ["windows:sysmon"]
    assert t1078["uncovered_in"] == ["OktaIM2:log"]
