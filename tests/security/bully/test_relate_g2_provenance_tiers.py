"""G.2 -- anchor provenance tiers, revocation, and depth: a depth-capped
chain stops contributing; an override cascades; a SYSTEM_GENERATED anchor
cannot raise confidence or enter scoring truth."""

from __future__ import annotations

from portal.modules.security.core.bully import provenance
from portal.modules.security.core.bully.anchors import AnchorLibrary, make_anchor


def test_system_generated_anchor_cannot_raise_confidence():
    anchor = make_anchor(
        "confirmed_finding",
        {},
        source_id="observed-mode",
        label_basis=None,
        provenance_tier="SYSTEM_GENERATED",
    )
    assert provenance.can_raise_confidence(anchor) is False
    assert provenance.context_only(anchor) is True


def test_external_and_analyst_confirmed_within_depth_cap_can_raise_confidence():
    external = make_anchor("attack_episode", {}, source_id="attack_data", label_basis="data_yml")
    analyst = make_anchor(
        "confirmed_finding",
        {},
        source_id="investigation",
        label_basis="analyst_decision",
        provenance_tier="ANALYST_CONFIRMED",
        generation_depth=1,
    )
    assert provenance.can_raise_confidence(external) is True
    assert provenance.can_raise_confidence(analyst) is True


def test_depth_capped_chain_stops_contributing():
    beyond_cap = make_anchor(
        "confirmed_finding",
        {},
        source_id="investigation",
        label_basis="analyst_decision",
        provenance_tier="ANALYST_CONFIRMED",
        generation_depth=2,  # derived from an outcome that leaned on a
        # SYSTEM_GENERATED anchor -- past MAX_GENERATION_DEPTH
    )
    assert provenance.can_raise_confidence(beyond_cap) is False
    assert provenance.context_only(beyond_cap) is True


def test_override_cascades_to_derived_anchors():
    lib = AnchorLibrary()
    root = lib.load_confirmed_finding(
        source_id="investigation",
        record={"context_topology": {"target_host": "web01"}},
        outcome="ESCALATE",
        analyst_confirmed=True,
    )
    child = lib.add(
        make_anchor(
            "confirmed_finding",
            {"context_topology": {"target_host": "web02"}},
            source_id="investigation",
            label_basis="analyst_decision",
            provenance_tier="ANALYST_CONFIRMED",
            derived_from=(root.anchor_id,),
            generation_depth=1,
        )
    )
    grandchild = lib.add(
        make_anchor(
            "confirmed_finding",
            {"context_topology": {"target_host": "web03"}},
            source_id="investigation",
            label_basis="analyst_decision",
            provenance_tier="ANALYST_CONFIRMED",
            derived_from=(child.anchor_id,),
            generation_depth=2,
        )
    )
    assert provenance.can_raise_confidence(root) is True
    assert provenance.can_raise_confidence(child) is True

    records = provenance.revoke_outcome(lib, root.anchor_id)
    record_anchor_ids = {r.anchor_id for r in records}
    assert {root.anchor_id, child.anchor_id, grandchild.anchor_id} <= record_anchor_ids
    assert all(r.outcome_anchor_id == root.anchor_id for r in records)

    demoted_root = lib.get(root.anchor_id)
    demoted_child = lib.get(child.anchor_id)
    assert demoted_root.provenance_tier == "SYSTEM_GENERATED"
    assert demoted_child.provenance_tier == "SYSTEM_GENERATED"
    assert provenance.can_raise_confidence(demoted_root) is False
    assert provenance.can_raise_confidence(demoted_child) is False


def test_revocation_does_not_touch_unrelated_anchors():
    lib = AnchorLibrary()
    root = lib.load_confirmed_finding(
        source_id="investigation", record={}, outcome="ESCALATE", analyst_confirmed=True
    )
    unrelated = lib.load_attack_episode(
        source_id="attack_data",
        record={"action_sequence": ["proc_create"]},
        techniques=("T1059",),
    )
    provenance.revoke_outcome(lib, root.anchor_id)
    assert lib.get(unrelated.anchor_id).provenance_tier == "EXTERNAL"
