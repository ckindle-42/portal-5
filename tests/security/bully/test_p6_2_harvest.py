"""P6.2 -- HARV: leakage-safe role-tagged corpus + dataset versions (M8).

Hermetic (`tmp_path`, no network). Feeds C11 HARV: below-floor non-build;
leakage/duplicate quarantine; content-hash determinism. The BM import-scan
guard (bully package cannot import recall_attribution) is covered generically
by test_boundaries.py's glob over BULLY_DIR -- harvest.py is included there
automatically.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import harvest
from portal.modules.security.core.bully.contracts import DecisionEvent
from portal.modules.security.core.bully.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _emit(store, *, event_id, hunt_id, kind, subject_id, rationale, data=None):
    store.record_decision(
        DecisionEvent(
            event_id=event_id,
            hunt_id=hunt_id,
            iteration_id=None,
            actor="system:test",
            kind=kind,
            subject_id=subject_id,
            rationale=rationale,
            data=data or {},
        )
    )


# ── append_pairs: role mapping + quarantine ────────────────────────────────


def test_append_pairs_maps_kinds_to_roles(store):
    _emit(
        store,
        event_id="e1",
        hunt_id="h1",
        kind="target_select",
        subject_id="c1",
        rationale="hunt here",
    )
    _emit(
        store,
        event_id="e2",
        hunt_id="h1",
        kind="kill",
        subject_id="c1",
        rationale="benign automation",
    )
    _emit(
        store,
        event_id="e3",
        hunt_id="h1",
        kind="grade",
        subject_id="a1",
        rationale="BR-COUSIN graded relationship=SAME",
        data={"trust_tier": "OPERATOR_CONFIRMED"},
    )
    n = harvest.append_pairs(store, "h1")
    assert n == 3
    hunter = store.training_examples_for_role("hunter")
    disprover = store.training_examples_for_role("disprover")
    cousin_smeller = store.training_examples_for_role("cousin_smeller")
    assert len(hunter) == 1
    assert len(disprover) == 1 and disprover[0]["is_negative"] == 1
    assert len(cousin_smeller) == 1 and cousin_smeller[0]["is_distance_pair"] == 1


def test_append_pairs_ignores_unmapped_kinds(store):
    _emit(
        store,
        event_id="e1",
        hunt_id="h1",
        kind="config",
        subject_id="h1",
        rationale="hunt authorized",
    )
    n = harvest.append_pairs(store, "h1")
    assert n == 0


def test_append_pairs_quarantines_missing_provenance(store):
    _emit(store, event_id="e1", hunt_id=None, kind="promote", subject_id="c1", rationale="promoted")
    harvest.append_pairs(store, None)
    all_examples = store.training_examples_for_role("analyst", include_quarantined=True)
    assert len(all_examples) == 1
    assert all_examples[0]["quarantine_reason"] == "missing_provenance"
    usable = store.training_examples_for_role("analyst")
    assert usable == []


def test_append_pairs_quarantines_suspect_trust_cousin_grade(store):
    _emit(
        store,
        event_id="e1",
        hunt_id="h1",
        kind="grade",
        subject_id="a1",
        rationale="graded",
        data={"trust_tier": "SUSPECT"},
    )
    harvest.append_pairs(store, "h1")
    all_examples = store.training_examples_for_role("cousin_smeller", include_quarantined=True)
    assert all_examples[0]["quarantine_reason"] == "suspect_trust:'SUSPECT'"
    assert store.training_examples_for_role("cousin_smeller") == []


def test_append_pairs_quarantines_exact_duplicate_input(store):
    # Same kind/subject_id/data (minus rationale) -> identical input_text.
    _emit(
        store,
        event_id="e1",
        hunt_id="h1",
        kind="target_select",
        subject_id="c1",
        rationale="r1",
        data={"x": 1},
    )
    _emit(
        store,
        event_id="e2",
        hunt_id="h1",
        kind="target_select",
        subject_id="c1",
        rationale="r2",
        data={"x": 1},
    )
    harvest.append_pairs(store, "h1")
    all_examples = store.training_examples_for_role("hunter", include_quarantined=True)
    assert len(all_examples) == 2
    reasons = sorted(e["quarantine_reason"] or "" for e in all_examples)
    assert reasons == ["", "duplicate"]


def test_append_pairs_is_idempotent_on_reharvest(store):
    _emit(
        store,
        event_id="e1",
        hunt_id="h1",
        kind="promote",
        subject_id="c1",
        rationale="promoted, clean",
    )
    n1 = harvest.append_pairs(store, "h1")
    n2 = harvest.append_pairs(store, "h1")
    assert n1 == n2 == 1
    assert len(store.training_examples_for_role("analyst")) == 1  # no duplicate row


# ── build_dataset: below-floor / content-hash determinism ─────────────────


def test_build_dataset_below_floor_is_honest_non_build(store):
    for i in range(3):
        _emit(
            store,
            event_id=f"e{i}",
            hunt_id="h1",
            kind="promote",
            subject_id=f"c{i}",
            rationale=f"promoted {i}",
        )
    harvest.append_pairs(store, "h1")
    ref = harvest.build_dataset(store, "analyst", {"since": 0}, min_size=20)
    assert ref["built"] is False
    assert "below size floor" in ref["reason"]
    assert ref.get("dataset_version") is None  # no dataset_version row created


def test_build_dataset_content_hash_is_deterministic(store, tmp_path):
    for i in range(5):
        _emit(
            store,
            event_id=f"e{i}",
            hunt_id="h1",
            kind="promote",
            subject_id=f"c{i}",
            rationale=f"promoted {i}",
        )
    harvest.append_pairs(store, "h1")

    corpus_root = tmp_path / "corpus" / "analyst"
    ref1 = harvest.build_dataset(
        store, "analyst", {"since": 0}, min_size=3, corpus_root=corpus_root
    )
    ref2 = harvest.build_dataset(
        store, "analyst", {"since": 0}, min_size=3, corpus_root=corpus_root
    )

    assert ref1["built"] is True
    assert ref1["dataset_version"] == ref2["dataset_version"]
    assert ref1["newly_inserted"] is True
    assert ref2["newly_inserted"] is False  # same window+config -> same content hash, no-op

    row = store.dataset_version_get(ref1["dataset_version"])
    assert row is not None
    assert row["counts"]["total"] == 5


def test_build_dataset_changes_hash_when_examples_change(store, tmp_path):
    for i in range(5):
        _emit(
            store,
            event_id=f"e{i}",
            hunt_id="h1",
            kind="promote",
            subject_id=f"c{i}",
            rationale=f"promoted {i}",
        )
    harvest.append_pairs(store, "h1")
    corpus_root = tmp_path / "corpus" / "analyst"
    ref1 = harvest.build_dataset(
        store, "analyst", {"since": 0}, min_size=3, corpus_root=corpus_root
    )

    _emit(
        store, event_id="e5", hunt_id="h1", kind="promote", subject_id="c5", rationale="promoted 5"
    )
    harvest.append_pairs(store, "h1")
    ref2 = harvest.build_dataset(
        store, "analyst", {"since": 0}, min_size=3, corpus_root=corpus_root
    )

    assert ref1["dataset_version"] != ref2["dataset_version"]


def test_build_dataset_rejects_unknown_role(store):
    with pytest.raises(harvest.HarvestError):
        harvest.build_dataset(store, "not-a-role", {})
