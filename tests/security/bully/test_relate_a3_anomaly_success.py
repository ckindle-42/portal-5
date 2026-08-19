"""A.3 -- ANOMALOUS_UNCLASSIFIED as a first-class relation outcome.

A novel synthetic behaviour yields ANOMALOUS with a distance profile, not
silence; a benign-ordinary (well-matched) neighbourhood does not.
"""

from __future__ import annotations

from portal.modules.security.core.bully import relation as relation_mod
from portal.modules.security.core.bully import signatures as sig_mod
from portal.modules.security.core.bully.anchors import AnchorLibrary


def _populated_library() -> AnchorLibrary:
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create", "net_connect"]},
        techniques=("T1059",),
    )
    lib.load_detection_coverage(
        source_id="detection_lib",
        detection_id="det-001",
        techniques=("T1059",),
        telemetry_shape={"source_class": "edr"},
    )
    return lib


def _rich_library() -> AnchorLibrary:
    """Anchors with every axis populated, so a fully disjoint subject drives
    the composite distance up across all of them (rather than the axes just
    being unavailable and excluded from the composite)."""
    lib = AnchorLibrary()
    lib.load_attack_episode(
        source_id="attack_data",
        record={
            "action_sequence": ["proc_create", "net_connect"],
            "telemetry_shape": {"source_class": "wmi"},
            "context_topology": {"zone": "prod"},
        },
        techniques=("T1059",),
    )
    return lib


def test_novel_synthetic_behaviour_yields_anomalous_with_distance_profile():
    lib = _rich_library()
    novel = sig_mod.build_signature(
        {"target_host": "zeta9"},
        {
            "action_sequence": ["exotic_process_hollow", "exotic_beacon_channel"],
            "attack_mappings": [{"technique_id": "T9999"}],
            "telemetry_shape": {"source_class": "novel_sensor"},
            "context_topology": {"zone": "quarantine"},
        },
    )
    rel = relation_mod.relate(novel, lib)
    assert rel.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert rel.distance_profile is not None
    assert rel.distance_profile["composite"] is not None
    assert "novel_behavior:no_anchor_match" in rel.uncertainty_reasons


def test_benign_ordinary_neighbourhood_does_not_yield_anomalous():
    lib = _populated_library()
    matching = sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )
    rel = relation_mod.relate(matching, lib)
    assert rel.verdict != "ANOMALOUS_UNCLASSIFIED"
    assert rel.distance_profile is None
