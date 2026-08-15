"""P3.1/P3.3 -- MUT wired into LOOP's MUTATION_READY -> EXECUTING stage
(replacing the P1 stub).

Hermetic (tmp_path Store/Organ, injected lab_driver/investigation_arm -- no
network, no real lab). FINAL_VALIDATION C9 (mutation director wired into the
real loop) + M1/M2 (mutation shadow producing records; Red source untouched
-- proven separately by `test_boundaries.py`'s import-scan).
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.contracts import MutationOperatorSpec
from portal.modules.security.core.bully.investigation import InvestigationResult
from portal.modules.security.core.bully.mutation import build_plan
from portal.modules.security.core.bully.organ import Organ
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


def _proven_episode(scenario="kerberoast_to_da") -> Episode:
    return Episode(
        episode_id="ep-20260101T000000Z-scn-abcd1234",
        scenario=scenario,
        target_host="10.10.11.21",
        started_at=0.0,
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_INDEXED",
        detection_status="DETECTION_CONFIRMED",
    )


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


def _make_hunt(store, hunt_id="hunt-1"):
    store.hunt_create(
        hunt_id=hunt_id,
        objective="prove cousin discovery",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire(hunt_id, owner="operator:alice")


def test_mutation_plan_is_compiled_and_persisted_every_iteration(store, organ):
    _make_hunt(store)
    captured_target_cells = []

    def _driver(target_cell, *, dry_run):
        captured_target_cells.append(target_cell)
        return _proven_episode()

    result = orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-1",
        actor="operator:alice",
        neighborhood="lab-default",
        lab_driver=_driver,
        investigation_arm=_fake_investigation_arm,
    )

    assert result["stage"] == "CLOSED"
    n_plans = store._conn.execute("SELECT COUNT(*) AS n FROM mutation_plans").fetchone()["n"]
    assert n_plans == 1
    row = store._conn.execute("SELECT status FROM mutation_plans LIMIT 1").fetchone()
    assert row["status"] == "validated"
    # The overlay reached the lab driver as data on target_cell.
    assert "mutation_overlay" in captured_target_cells[0]


def test_injected_mutation_plan_overlay_reaches_the_lab_driver(store, organ):
    _make_hunt(store)
    captured = {}

    def _driver(target_cell, *, dry_run):
        captured["overlay"] = target_cell.get("mutation_overlay")
        return _proven_episode()

    plan = build_plan(
        reference_scenario="kerberoast_to_da",
        operators=[
            MutationOperatorSpec(
                operator="SUBSTITUTE_TECHNIQUE",
                params={"from": "establish_persistence", "to": "establish_persistence_alt"},
            )
        ],
        allowed_targets=("10.10.11.21",),
        proposer="operator:alice",
    )

    orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-1",
        actor="operator:alice",
        neighborhood="lab-default",
        target_cell={"scenario": "kerberoast_to_da"},
        lab_driver=_driver,
        investigation_arm=_fake_investigation_arm,
        mutation_plan=plan,
    )

    assert captured["overlay"] is not None
    assert "establish_persistence_alt" in captured["overlay"]["red_order"]
    assert "establish_persistence" not in captured["overlay"]["red_order"]


def test_out_of_scope_mutation_plan_blocks_honestly_no_red_call(store, organ):
    _make_hunt(store)
    driver_called = []

    def _driver(target_cell, *, dry_run):
        driver_called.append(True)
        return _proven_episode()

    plan = build_plan(
        reference_scenario="kerberoast_to_da",
        operators=[],
        allowed_targets=("8.8.8.8",),  # outside LAB_CIDR
        proposer="operator:alice",
    )

    with pytest.raises(orch.HonestBlockedError):
        orch.run_hunt_iteration(
            store,
            organ,
            hunt_id="hunt-1",
            actor="operator:alice",
            neighborhood="lab-default",
            target_cell={"scenario": "kerberoast_to_da"},
            lab_driver=_driver,
            investigation_arm=_fake_investigation_arm,
            mutation_plan=plan,
        )

    assert driver_called == []  # Red machinery never invoked
    row = store.hunt_get("hunt-1")
    assert row["stage"] == "BLOCKED"
    rejected = store._conn.execute(
        "SELECT status, rejection_reason_code FROM mutation_plans WHERE plan_id=?", (plan.plan_id,)
    ).fetchone()
    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason_code"] == "SCOPE_VIOLATION"
