"""N.1 -- benign types are first-class known types (TASK_BULLY_UNKNOWN_COUSIN_V1)."""

from __future__ import annotations

from portal.modules.security.core.bully import anchors


def test_benign_pattern_is_a_registered_anchor_kind():
    assert "benign_pattern" in anchors.ANCHOR_KINDS


def test_malicious_kinds_default_to_malicious_malice():
    library = anchors.AnchorLibrary()
    anchor = library.load_attack_episode(source_id="s1", record={}, techniques=("T1078",))
    assert anchor.malice == "malicious"


def test_benign_pattern_anchor_carries_benign_malice():
    library = anchors.AnchorLibrary()
    anchor = library.load_benign_pattern(
        source_id="corpus", record={"action_sequence": ["enumerate"]}, recurrence_count=5
    )
    assert anchor.malice == "benign"
    assert anchor.grade in anchors.ANCHOR_GRADES


def test_benign_pattern_with_no_recurrence_stores_weak_never_dropped():
    library = anchors.AnchorLibrary()
    anchor = library.load_benign_pattern(
        source_id="corpus", record={"action_sequence": ["auth"]}, recurrence_count=0
    )
    assert anchor.grade == "weak"
    assert anchor in library.by_kind("benign_pattern")


def test_make_anchor_rejects_unknown_malice_value():
    try:
        anchors.make_anchor("attack_episode", {}, source_id="s1", malice="evil")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown malice value")


def test_derive_recurring_benign_patterns_keeps_only_recurring_shapes():
    # Users recur (2 identities) rather than being unique per record: a
    # near-unique-per-record field is a record id under field-role inference
    # (E.1/E.2), not a pivotable entity -- correctly, since real benign
    # corpora recur by identity, which is exactly the premise this test
    # exists to check.
    records = [
        {
            "eventName": "ListBuckets",
            "user": f"u{i % 2}",
            "eventTime": 1_700_000_000.0 + float(i),
        }
        for i in range(5)
    ] + [{"eventName": "AssumeRole", "user": "one-off", "eventTime": 1_700_000_100.0}]
    patterns = anchors.derive_recurring_benign_patterns(records, min_recurrence=3)
    assert patterns
    assert all(p["recurrence_count"] >= 3 for p in patterns)
    assert all(p["action_sequence"] == ["enumerate"] for p in patterns)


def test_composition_report_includes_benign_pattern_kind():
    library = anchors.AnchorLibrary()
    library.load_benign_pattern(source_id="corpus", record={}, recurrence_count=4)
    comp = library.composition()
    assert "benign_pattern" in comp
