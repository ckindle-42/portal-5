"""A.1 -- anchor library: all four kinds load; an anchor without label basis
is stored as weak, not rejected; grades differ."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors as anchors_mod


def _populated_library() -> anchors_mod.AnchorLibrary:
    lib = anchors_mod.AnchorLibrary()
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
    lib.load_confirmed_finding(
        source_id="investigation",
        record={"context_topology": {"target_host": "web01"}},
        outcome="ESCALATE",
        analyst_confirmed=True,
    )
    return lib


def test_all_four_anchor_kinds_load():
    lib = _populated_library()
    kinds_present = {a.kind for a in lib.all()}
    assert kinds_present == set(anchors_mod.ANCHOR_KINDS)
    assert len(lib) == 4


def test_anchor_without_label_basis_is_weak_not_rejected():
    lib = anchors_mod.AnchorLibrary()
    anchor = lib.load_advisory(source_id="advisory_feed", technique=None)
    assert anchor.grade == "weak"
    assert anchor in lib.all()
    assert lib.get(anchor.anchor_id) is anchor


def test_grades_differ_across_anchors():
    lib = _populated_library()
    grades = {a.grade for a in lib.all()}
    assert len(grades) > 1


def test_unreviewed_confirmed_finding_is_weak_and_system_generated():
    lib = anchors_mod.AnchorLibrary()
    anchor = lib.load_confirmed_finding(
        source_id="investigation",
        record={},
        outcome="BENIGN_CLOSE",
        analyst_confirmed=False,
    )
    assert anchor.grade == "weak"
    assert anchor.provenance_tier == "SYSTEM_GENERATED"


def test_records_view_matches_cousin_engine_reference_shape():
    lib = _populated_library()
    records = lib.records()
    assert all("record_id" in r for r in records)
    episode_records = lib.records(kinds=("attack_episode",))
    assert len(episode_records) == 1
    assert episode_records[0]["attack_mappings"][0]["technique_id"] == "T1059"


def test_composition_reports_kind_and_grade_counts():
    lib = _populated_library()
    comp = lib.composition()
    assert set(comp) == set(anchors_mod.ANCHOR_KINDS)
    assert comp["attack_episode"]["strong"] == 1
