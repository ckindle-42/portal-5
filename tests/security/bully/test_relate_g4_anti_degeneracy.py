"""G.4 -- anti-degeneracy guards for anomaly, uncertainty, and density: each
degeneracy is seeded and caught; density-capped confidence is enforced."""

from __future__ import annotations

from types import SimpleNamespace

from portal.modules.security.core.bully import degeneracy
from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary


def _relation_stub(verdict: str, reasons: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(verdict=verdict, uncertainty_reasons=reasons)


def test_anomaly_inflation_rate_ceiling_is_caught():
    relations = [_relation_stub("ANOMALOUS_UNCLASSIFIED", ()) for _ in range(8)]
    relations += [_relation_stub("SAME", ()) for _ in range(2)]
    finding = degeneracy.check_anomaly_rate(relations)
    assert finding.rate == 0.8
    assert finding.exceeded is True


def test_healthy_anomaly_rate_is_not_flagged():
    relations = [_relation_stub("ANOMALOUS_UNCLASSIFIED", ()) for _ in range(2)]
    relations += [_relation_stub("SAME", ()) for _ in range(8)]
    finding = degeneracy.check_anomaly_rate(relations)
    assert finding.exceeded is False


def test_boilerplate_uncertainty_is_caught_by_variance_check():
    boilerplate = ("thin_anchor_coverage:0_candidates",)
    relations = [_relation_stub("NEW", boilerplate) for _ in range(10)]
    report = degeneracy.check_uncertainty_variance(relations)
    assert report.passes is False
    assert report.max_repeat_fraction == 1.0


def test_varying_uncertainty_passes_the_variance_check():
    relations = [_relation_stub("NEW", (f"missing_dimension:axis-{i % 5}",)) for i in range(10)]
    report = degeneracy.check_uncertainty_variance(relations)
    assert report.passes is True
    assert report.distinct_reason_sets > 1


def test_density_capped_confidence_enforced_in_sparse_region():
    assert degeneracy.density_capped_confidence(0.9, anchor_count=1, floor=3) < 0.9
    assert degeneracy.density_capped_confidence(0.9, anchor_count=1, floor=3) <= 1 / 3
    assert degeneracy.density_capped_confidence(0.9, anchor_count=5, floor=3) == 0.9


def test_far_nearest_anchor_forces_anomalous_not_stretched_match():
    verdict, confidence = degeneracy.apply_density_guard(
        "NEW", 0.7, nearest_distance=0.95, anchor_count=5
    )
    assert verdict == "ANOMALOUS_UNCLASSIFIED"

    unchanged_verdict, _ = degeneracy.apply_density_guard(
        "NEW", 0.7, nearest_distance=0.4, anchor_count=5
    )
    assert unchanged_verdict == "NEW"


def test_sparse_anchor_library_caps_confidence_in_live_relate():
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create", "net_connect"]},
        techniques=("T1059",),
    )
    signature = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    rel = relation_mod.relate(signature, lib)
    # Only one anchor was ever loaded -- density (below DENSITY_FLOOR) caps
    # confidence regardless of how tight the composite-distance match is.
    assert len(rel.anchors_considered) < degeneracy.DENSITY_FLOOR
    assert rel.confidence <= len(rel.anchors_considered) / degeneracy.DENSITY_FLOOR
