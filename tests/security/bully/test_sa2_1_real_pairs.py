from __future__ import annotations

import ast
import inspect

from portal.modules.security.core.bully import discovery_bench
from tests.security.bully._discovery_fixtures import build_corpus, build_snapshot


def test_real_probe_specimens_draws_attack_data_lane_only():
    corpus = build_corpus()
    corpus["specimens"].append(
        {
            "specimen_id": "forge-child",
            "source_lane": "replay_mutation",
            "source_class": "windows:sysmon",
            "engine_view": corpus["specimens"][0]["engine_view"],
        }
    )
    probes = discovery_bench.real_probe_specimens(corpus)
    assert {p["specimen_id"] for p in probes} == {
        "sysmon-kerberoast",
        "sysmon-unrelated",
        "okta-kerberoast-cousin",
        "okta-unrelated",
        "sysmon-t1078-fired",
        "okta-t1078-missed",
        "sysmon-t1021-lateral",
        "okta-t1021-cousin",
    }
    assert "forge-child" not in {p["specimen_id"] for p in probes}


def test_no_forge_operator_touches_the_discovery_module_source():
    """A1/A2: static guard -- the discovery_bench module must never import
    the forge (mutation/cousin_forge) it is required to stay independent of."""
    source = inspect.getsource(discovery_bench)
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.add(node.module or "")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
    forbidden = {"mutation", "cousin_forge", ".mutation", ".cousin_forge"}
    assert not (imported_names & forbidden), imported_names


def test_grade_real_pair_engine_receives_no_truth_labels(monkeypatch):
    """The engine call (`cousin_engine.grade`) is given a signature built
    purely from `engine_view` (telemetry + trust tier) and a candidate set --
    never `truth_related`, `technique_ids`-as-truth, or any scorer label."""
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    index_by_id = {s["specimen_id"]: s for s in corpus["specimens"]}

    seen_kwargs = []
    from portal.modules.security.core.bully import cousin_engine

    real_grade = cousin_engine.grade

    def spy_grade(signature, candidates, coverage, **kwargs):
        seen_kwargs.append(kwargs)
        assert not hasattr(signature, "truth_related")
        assert not hasattr(coverage, "truth_related")
        return real_grade(signature, candidates, coverage, **kwargs)

    monkeypatch.setattr(discovery_bench.cousin_engine, "grade", spy_grade)
    for probe in probes:
        discovery_bench.grade_real_pair(probe, snapshot, index_by_id=index_by_id)
    assert len(seen_kwargs) == len(probes)


def test_pairs_span_classes():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    verdicts = discovery_bench.run_real_pairs(probes, snapshot, corpus=corpus)
    classes_seen = {v.reference_source_class for v in verdicts if v.reference_source_class}
    assert len(classes_seen) >= 2, "candidates must be reachable across classes (no class filter)"
    assert any(v.cross_class for v in verdicts)


def test_self_exclusion_prevents_trivial_same_match():
    corpus = build_corpus()
    snapshot = build_snapshot(corpus)
    probes = discovery_bench.real_probe_specimens(corpus)
    index_by_id = {s["specimen_id"]: s for s in corpus["specimens"]}
    for probe in probes:
        verdict = discovery_bench.grade_real_pair(probe, snapshot, index_by_id=index_by_id)
        assert verdict.reference_signature_id != probe["specimen_id"]
