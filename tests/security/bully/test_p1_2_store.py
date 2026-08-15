"""P1.2 -- SUB store, ordered migrations, hash-chained events, outbox.

Hermetic (`tmp_path`, no network) per the project testing rules and
FINAL_VALIDATION C1 ("SUB is restart-safe, append-only, state-machine
enforced") + C3 ("outbox, projection, and recall" -- store side).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from portal.modules.security.core.bully import events
from portal.modules.security.core.bully.contracts import DecisionEvent, new_id
from portal.modules.security.core.bully.store import (
    IllegalTransitionError,
    LeaseError,
    OutboxIntegrityError,
    Store,
)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


def _make_hunt(store, hunt_id="hunt-1"):
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="auth-1",
        config_version="cfg-1",
        role_snapshot={"investigator": "some-tag"},
        budgets={"max_iterations": 5},
    )


# ── migrations ────────────────────────────────────────────────────────────


def test_migration_idempotent_replay(tmp_path):
    db_path = tmp_path / "hunt_state.db"
    s1 = Store(db_path)
    s1.close()
    # Reopening must not re-apply any already-applied migration file (which
    # would fail on `CREATE TABLE` of an already-existing table if it did).
    # The expected count tracks however many migration files ship on disk
    # (001_init.sql in P1, +002_bin_heart.sql from P2, ...) rather than a
    # value hardcoded at P1 time.
    from portal.modules.security.core.bully.store import _MIGRATIONS_DIR

    expected = len(list(_MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")))
    s2 = Store(db_path)
    row = s2._conn.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()
    assert row["n"] == expected
    s2.close()


def test_migration_ledger_tracks_applied_version(store):
    row = store._conn.execute("SELECT version, filename FROM schema_migrations").fetchone()
    assert row["version"] == 1
    assert row["filename"] == "001_init.sql"


# ── hunts / stage machine (C1) ──────────────────────────────────────────────


def test_hunt_create_and_load_context(store):
    _make_hunt(store)
    ctx = store.load_context("hunt-1")
    assert ctx.hunt_id == "hunt-1"
    assert ctx.neighborhood_scope == "lab-default"


def test_legal_transition_succeeds(store):
    _make_hunt(store)
    store.hunt_advance_stage("hunt-1", "AUTHORIZED", expected_version=0)
    row = store.hunt_get("hunt-1")
    assert row["stage"] == "AUTHORIZED"
    assert row["version"] == 1


def test_illegal_backward_transition_rejected(store):
    _make_hunt(store)
    store.hunt_advance_stage("hunt-1", "AUTHORIZED", expected_version=0)
    with pytest.raises(IllegalTransitionError):
        store.hunt_advance_stage("hunt-1", "DRAFT", expected_version=1)
    # state unchanged after the rejected attempt
    row = store.hunt_get("hunt-1")
    assert row["stage"] == "AUTHORIZED"


def test_stale_expected_version_rejected(store):
    _make_hunt(store)
    store.hunt_advance_stage("hunt-1", "AUTHORIZED", expected_version=0)
    with pytest.raises(IllegalTransitionError):
        store.hunt_advance_stage("hunt-1", "RECALL_READY", expected_version=0)  # stale


def test_terminal_stage_is_sealed(store):
    _make_hunt(store)
    for target in (
        "AUTHORIZED",
        "RECALL_READY",
        "TARGETED",
        "MUTATION_READY",
        "EXECUTING",
        "ANALYZING",
        "PROMOTING",
        "COMPOUNDING",
        "CLOSED",
    ):
        row = store.hunt_get("hunt-1")
        store.hunt_advance_stage("hunt-1", target, expected_version=row["version"])
    with pytest.raises(IllegalTransitionError):
        row = store.hunt_get("hunt-1")
        store.hunt_advance_stage("hunt-1", "BLOCKED", expected_version=row["version"])


# ── leases ────────────────────────────────────────────────────────────────


def test_lease_uniqueness(store):
    _make_hunt(store)
    store.lease_acquire("hunt-1", owner="worker-a")
    with pytest.raises(LeaseError):
        store.lease_acquire("hunt-1", owner="worker-b")


def test_lease_release_then_reacquire(store):
    _make_hunt(store)
    store.lease_acquire("hunt-1", owner="worker-a")
    store.lease_release("hunt-1", owner="worker-a")
    store.lease_acquire("hunt-1", owner="worker-b")  # no longer conflicts
    row = store.hunt_get("hunt-1")
    assert row["lease_owner"] == "worker-b"


# ── decision events / hash chain (C1) ───────────────────────────────────────


def _event(hunt_id="hunt-1", subject="s1", rationale="because") -> DecisionEvent:
    return DecisionEvent(
        event_id=new_id("de"),
        hunt_id=hunt_id,
        iteration_id=None,
        actor="system:test",
        kind="target_select",
        subject_id=subject,
        rationale=rationale,
    )


def test_decision_log_is_append_only_and_chained(store):
    _make_hunt(store)
    e1 = store.record_decision(_event(rationale="first"))
    e2 = store.record_decision(_event(rationale="second"))
    assert e1.chain_hash != e2.chain_hash
    assert e2.prev_event_hash == e1.chain_hash

    evs = store.decision_events_for_hunt("hunt-1")
    assert [e.event_id for e in evs] == [e1.event_id, e2.event_id]
    ok, broken = events.verify_chain(evs)
    assert ok and broken is None


def test_decision_log_rejects_update_and_delete(store):
    _make_hunt(store)
    store.record_decision(_event())
    with pytest.raises(sqlite3.DatabaseError):
        store._conn.execute("UPDATE decision_events SET rationale='tampered'")
    with pytest.raises(sqlite3.DatabaseError):
        store._conn.execute("DELETE FROM decision_events")


def test_tampering_is_detected_by_hash_chain_verification(store):
    _make_hunt(store)
    store.record_decision(_event(rationale="first"))
    store.record_decision(_event(rationale="second"))
    evs = store.decision_events_for_hunt("hunt-1")
    tampered = list(evs)
    tampered[0] = replace(tampered[0], rationale="TAMPERED")
    ok, broken = events.verify_chain(tampered)
    assert not ok
    assert broken == evs[0].event_id


# ── known_state supersede ────────────────────────────────────────────────


def test_known_state_supersede_never_deletes(store):
    _make_hunt(store)
    first = store.update_known_state(
        "cell-1", "known_benign", {"episode_id": "ep-1"}, hunt_id="hunt-1"
    )
    second = store.update_known_state(
        "cell-1", "contradicted", {"episode_id": "ep-2"}, hunt_id="hunt-1", supersedes=first
    )
    row_first = store._conn.execute(
        "SELECT * FROM known_state WHERE entry_id=?", (first,)
    ).fetchone()
    assert row_first["superseded_by"] == second
    row_second = store._conn.execute(
        "SELECT * FROM known_state WHERE entry_id=?", (second,)
    ).fetchone()
    assert row_second["superseded_by"] is None


def test_known_state_requires_evidence(store):
    _make_hunt(store)
    from portal.modules.security.core.bully.store import StoreError

    with pytest.raises(StoreError):
        store.update_known_state("cell-1", "known_benign", {}, hunt_id="hunt-1")


# ── outbox: lease -> complete -> dead-letter (C3) ───────────────────────────


def test_outbox_lease_complete_round_trip(store):
    oid = store.outbox_append(
        record_type="cousin",
        record_id="rec-1",
        record_version=0,
        projection_version="v1",
        source_hash="abc123",
        operation="upsert",
        required_for_closure=True,
        payload={"text": "..."},
    )
    leased = store.outbox_lease()
    assert leased[0]["outbox_id"] == oid
    assert leased[0]["status"] == "leased"
    store.outbox_complete(oid, source_hash="abc123")
    row = store._conn.execute(
        "SELECT status FROM index_outbox WHERE outbox_id=?", (oid,)
    ).fetchone()
    assert row["status"] == "completed"


def test_outbox_complete_rejects_source_hash_mismatch(store):
    oid = store.outbox_append(
        record_type="cousin",
        record_id="rec-1",
        record_version=0,
        projection_version="v1",
        source_hash="abc123",
        operation="upsert",
        required_for_closure=True,
        payload={},
    )
    with pytest.raises(OutboxIntegrityError):
        store.outbox_complete(oid, source_hash="WRONG")


def test_outbox_dead_letters_after_max_attempts(store):
    oid = store.outbox_append(
        record_type="cousin",
        record_id="rec-1",
        record_version=0,
        projection_version="v1",
        source_hash="abc123",
        operation="upsert",
        required_for_closure=True,
        payload={},
    )
    for _ in range(10):
        store.outbox_fail(oid, error="embed unreachable")
    row = store._conn.execute(
        "SELECT status FROM index_outbox WHERE outbox_id=?", (oid,)
    ).fetchone()
    assert row["status"] == "dead_letter"
    dead = store.outbox_required_dead_letters()
    assert any(d["outbox_id"] == oid for d in dead)


# ── doctor ────────────────────────────────────────────────────────────────


def test_doctor_reports_ok_on_healthy_db(store):
    _make_hunt(store)
    store.record_decision(_event())
    report = store.doctor()
    assert report["ok"] is True
    assert report["issues"] == []


def test_doctor_reports_broken_chain_on_corrupted_db(store):
    _make_hunt(store)
    store.record_decision(_event())
    # Simulate on-disk corruption/tampering bypassing the append-only
    # trigger (the trigger proves normal SQL can't do this; doctor must
    # still catch a row that was corrupted some other way, e.g. a restored
    # backup byte-flip).
    store._conn.execute("DROP TRIGGER trg_decision_events_no_update")
    store._conn.execute("UPDATE decision_events SET rationale='corrupted' WHERE hunt_id='hunt-1'")
    report = store.doctor()
    assert report["ok"] is False
    assert any("hash chain broken" in issue for issue in report["issues"])


def test_doctor_reports_required_dead_letters(store):
    oid = store.outbox_append(
        record_type="cousin",
        record_id="rec-1",
        record_version=0,
        projection_version="v1",
        source_hash="abc123",
        operation="upsert",
        required_for_closure=True,
        payload={},
    )
    for _ in range(10):
        store.outbox_fail(oid, error="down")
    report = store.doctor()
    assert report["ok"] is False
    assert any("dead letter" in issue for issue in report["issues"])
