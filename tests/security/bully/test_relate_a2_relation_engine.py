"""A.2 -- relation engine: grade a stream neighbourhood against anchors.

An opaque-entity source relates via structure with the semantic axis
contributing ~nothing; every relation carries itemised uncertainty; a
thin-anchor region yields low confidence rather than a confident guess.
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
    lib.load_advisory(
        source_id="advisory_feed",
        technique="T1566",
        ioc={"domain": "evil.example"},
        context={"target_host": "mail01"},
    )
    lib.load_detection_coverage(
        source_id="detection_lib",
        detection_id="det-001",
        techniques=("T1059",),
        telemetry_shape={"source_class": "edr"},
    )
    return lib


def _subject_signature():
    return sig_mod.build_signature(
        {"target_host": "host1"},
        {
            "action_sequence": ["proc_create", "net_connect"],
            "attack_mappings": [{"technique_id": "T1059"}],
        },
    )


def test_opaque_source_semantic_axis_contributes_nothing():
    lib = _populated_library()
    signature = _subject_signature()

    opaque = relation_mod.relate(signature, lib, capabilities={"semantic_text": False})
    text_capable = relation_mod.relate(signature, lib, capabilities={"semantic_text": True})

    assert opaque.axis_contributions["semantic"] == 0.0
    assert opaque.uncertainty_reasons and "opaque_entities:semantic_axis_unusable" in (
        opaque.uncertainty_reasons
    )
    # the structural axes still carry weight for the opaque source
    assert sum(
        w
        for axis, w in relation_mod.capability_weights({"semantic_text": False}).items()
        if axis != "semantic"
    ) > sum(
        w
        for axis, w in relation_mod.capability_weights({"semantic_text": True}).items()
        if axis != "semantic"
    )
    assert text_capable.axis_contributions["semantic"] is not None


def test_every_relation_carries_itemised_uncertainty():
    lib = _populated_library()
    signature = _subject_signature()
    rel = relation_mod.relate(signature, lib, capabilities={"semantic_text": True})
    assert isinstance(rel.uncertainty_reasons, tuple)
    assert len(rel.uncertainty_reasons) > 0
    # reasons are itemised, not a single boilerplate string
    assert len(set(rel.uncertainty_reasons)) == len(rel.uncertainty_reasons)


def test_thin_anchor_region_yields_low_confidence_not_confident_guess():
    empty_lib = AnchorLibrary()
    signature = _subject_signature()
    rel = relation_mod.relate(signature, empty_lib)
    assert rel.verdict == "ANOMALOUS_UNCLASSIFIED"
    assert rel.confidence == 0.0
    assert any(r.startswith("thin_anchor_coverage") for r in rel.uncertainty_reasons)


def test_anchors_considered_reflects_candidate_set():
    lib = _populated_library()
    signature = _subject_signature()
    rel = relation_mod.relate(signature, lib)
    assert set(rel.anchors_considered) <= {a.anchor_id for a in lib.all()}
    assert len(rel.anchors_considered) > 0
