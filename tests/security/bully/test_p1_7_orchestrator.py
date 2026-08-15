"""P1.7 -- LOOP orchestrator, full iteration E2E on the synthetic lab.

FINAL_VALIDATION I2 (hunt iteration E2E, mocked models + synthetic lab),
I2's enforcement claim (no RecallReceipt -> no targeting/grade; required
unindexed emission fails loudly), I2's budget claim, I3 (thin CLI/config),
C4 (deterministic calculations). `lab_driver` and `investigation_arm` are
injected fakes (the synthetic lab + mocked models the claim names); the
real orchestrator stage machine, SUB writes, and outbox emission all run
for real against a real (tmp_path) Store + Organ.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.investigation import InvestigationResult
from portal.modules.security.core.bully.organ import Organ, OrganUnavailable
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.episode import Episode


def _fake_embed(dim: int = 8):
    def _embed(texts):
        return [[float((hash(t) >> i) % 7) for i in range(dim)] for t in texts]

    return _embed


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "hunt_state.db")
    yield s
    s.close()


@pytest.fixture
def organ(tmp_path, store):
    o = Organ(store=store, db_path=tmp_path / "hunt_memory")
    o._embed = _fake_embed()
    yield o
    o.close()


def _proven_episode() -> Episode:
    return Episode(
        episode_id="ep-20260101T000000Z-scn-abcd1234",
        scenario="lateral-movement-wmi",
        target_host="host-1",
        started_at=0.0,
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_INDEXED",
        detection_status="DETECTION_CONFIRMED",
    )


def _synthetic_lab_driver(target_cell, *, dry_run):
    return _proven_episode()


def _fake_investigation_arm(episode, *, models, dry_run=False):
    return InvestigationResult(
        verdict="CONFIRMED",
        technique_ids=("T1021.002",),
        grounded_technique_ids=("T1021.002",),
        dropped_technique_ids=(),
        contradicted_technique_ids=(),
        reasoning="mocked investigation arm",
        match_grade="EXACT",
        evidence=("wmic process call create observed",),
    )


# ── I2 -- full E2E on the synthetic lab ──────────────────────────────────────


def test_full_iteration_e2e_synthetic_lab_and_mocked_models(store, organ):
    store.hunt_create(
        hunt_id="hunt-1",
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-1", owner="operator:alice")

    result = orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-1",
        actor="operator:alice",
        neighborhood="lab-default",
        lab_driver=_synthetic_lab_driver,
        investigation_arm=_fake_investigation_arm,
    )

    assert result["stage"] == "CLOSED"
    row = store.hunt_get("hunt-1")
    assert row["stage"] == "CLOSED"

    # SUB rows landed.
    assert store._conn.execute("SELECT COUNT(*) AS n FROM cousin_assessments").fetchone()["n"] == 1
    assert (
        store._conn.execute(
            "SELECT COUNT(*) AS n FROM decision_events WHERE hunt_id='hunt-1'"
        ).fetchone()["n"]
        >= 3
    )
    assert store.recall_receipt_exists("hunt-1")

    # Universal index emission proven: the outbox drained and the projection
    # actually received a row.
    assert result["outbox"]["completed"] == 1
    assert organ.stats()["row_count"] == 1


def test_run_hunt_top_level_entry_operator_gate_and_full_wiring(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL5_HUNT_DIR", str(tmp_path))
    with pytest.raises(orch.OperatorRequiredError):
        orch.run_hunt(actor="not-an-operator", lab_driver=_synthetic_lab_driver)

    store = Store(tmp_path / "hunt_state.db")
    organ = Organ(store=store, db_path=tmp_path / "hunt_memory")
    organ._embed = _fake_embed()
    try:
        report = orch.run_hunt(
            actor="operator:bob",
            store=store,
            organ=organ,
            lab_driver=_synthetic_lab_driver,
            investigation_arm=_fake_investigation_arm,
        )
        assert report["stage"] == "CLOSED"
        assert report["iterations"] == 1
        assert report["hunt_id"].startswith("hunt-")
    finally:
        organ.close()
        store.close()


# ── I2 enforcement -- no RecallReceipt -> no targeting/grade ───────────────


def test_no_recall_no_targeting_structural(store, organ, monkeypatch):
    store.hunt_create(
        hunt_id="hunt-2",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-2", owner="operator:alice")

    def _always_unavailable(**kwargs):
        raise OrganUnavailable("embed service unreachable")

    monkeypatch.setattr(organ, "recall", _always_unavailable)

    with pytest.raises(orch.HonestBlockedError):
        orch.run_hunt_iteration(
            store,
            organ,
            hunt_id="hunt-2",
            actor="operator:alice",
            neighborhood="lab-default",
            lab_driver=_synthetic_lab_driver,
            investigation_arm=_fake_investigation_arm,
        )

    row = store.hunt_get("hunt-2")
    assert row["stage"] == "BLOCKED"
    kinds = [
        r["kind"]
        for r in store._conn.execute(
            "SELECT kind FROM decision_events WHERE hunt_id='hunt-2'"
        ).fetchall()
    ]
    assert "target_select" not in kinds  # never reached TARGETED
    assert (
        store._conn.execute("SELECT COUNT(*) AS n FROM cousin_assessments").fetchone()["n"] == 0
    )  # never reached grading either


def test_required_dead_letter_blocks_closure(store, organ, monkeypatch):
    store.hunt_create(
        hunt_id="hunt-3",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-3", owner="operator:alice")

    monkeypatch.setattr(
        store, "outbox_required_dead_letters", lambda *a, **k: [{"outbox_id": "ob-x"}]
    )

    with pytest.raises(orch.HonestBlockedError, match="dead letter"):
        orch.run_hunt_iteration(
            store,
            organ,
            hunt_id="hunt-3",
            actor="operator:alice",
            neighborhood="lab-default",
            lab_driver=_synthetic_lab_driver,
            investigation_arm=_fake_investigation_arm,
        )
    row = store.hunt_get("hunt-3")
    assert row["stage"] == "BLOCKED"


def test_indeterminate_episode_blocks_never_scored(store, organ):
    store.hunt_create(
        hunt_id="hunt-4",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-4", owner="operator:alice")

    def _indeterminate_driver(target_cell, *, dry_run):
        return Episode(
            episode_id="ep-2",
            scenario="s",
            target_host="h",
            started_at=0.0,
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_COLLECTION_FAILED",
        )

    with pytest.raises(orch.HonestBlockedError, match="INDETERMINATE"):
        orch.run_hunt_iteration(
            store,
            organ,
            hunt_id="hunt-4",
            actor="operator:alice",
            neighborhood="lab-default",
            lab_driver=_indeterminate_driver,
            investigation_arm=_fake_investigation_arm,
        )
    row = store.hunt_get("hunt-4")
    assert row["stage"] == "BLOCKED"
    assert store._conn.execute("SELECT COUNT(*) AS n FROM cousin_assessments").fetchone()["n"] == 0


# ── I3 -- thin CLI/config ────────────────────────────────────────────────────


def test_hunt_status_no_operator_gate(store):
    store.hunt_create(
        hunt_id="hunt-5",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    report = orch.hunt_status("hunt-5", store=store)
    assert report["stage"] == "DRAFT"


def test_hunt_cancel_requires_operator_and_is_idempotent(store):
    store.hunt_create(
        hunt_id="hunt-6",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    with pytest.raises(orch.OperatorRequiredError):
        orch.cancel_hunt("hunt-6", actor="not-operator", store=store)

    r1 = orch.cancel_hunt("hunt-6", actor="operator:alice", store=store)
    assert r1["stage"] == "CANCELLED"
    r2 = orch.cancel_hunt("hunt-6", actor="operator:alice", store=store)  # idempotent, no raise
    assert r2["stage"] == "CANCELLED"


def test_hunt_doctor_thin_wrapper(store):
    report = orch.hunt_doctor(store=store)
    assert report["ok"] is True


def test_resume_and_queue_resolve_require_operator():
    with pytest.raises(orch.OperatorRequiredError):
        orch.resume_hunt("hunt-x", actor="not-operator")
    with pytest.raises(orch.OperatorRequiredError):
        orch.queue_resolve(item_id="q-1", actor="not-operator")


# ── C4 -- deterministic ──────────────────────────────────────────────────────


def test_iteration_id_is_deterministic_format(store, organ):
    store.hunt_create(
        hunt_id="hunt-7",
        objective="obj",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire("hunt-7", owner="operator:alice")
    result = orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-7",
        actor="operator:alice",
        neighborhood="lab-default",
        lab_driver=_synthetic_lab_driver,
        investigation_arm=_fake_investigation_arm,
    )
    assert result["iteration_id"] == "hunt-7-i1"
