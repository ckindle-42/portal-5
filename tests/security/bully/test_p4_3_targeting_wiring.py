"""P4.3 -- TGT wired into LOOP's TARGETED stage (replacing the P1 stub).

Hermetic (tmp_path Store/Organ, injected lab_driver/investigation_arm -- no
network, no real lab). FINAL_VALIDATION C10 TGT (wired) + R1 (targeting
live behavior): recall-influenced target selection and a cost-blocked
unrankable case, both with recorded factors.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.investigation import InvestigationResult
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


def _proven_episode(scenario) -> Episode:
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
        objective="prove recall-influenced targeting",
        neighborhood_scope="lab-default",
        authorization_ref="operator:alice",
        config_version="cfg-1",
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire(hunt_id, owner="operator:alice")


def test_targeting_selects_a_real_target_and_records_the_decision(store, organ):
    """TGT actually runs (not the P1 stub) and its choice reaches the lab
    driver as the iteration's scenario."""
    _make_hunt(store)
    captured = []

    def _driver(target_cell, *, dry_run):
        captured.append(target_cell)
        return _proven_episode(target_cell["scenario"])

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
    assert "target_decision_id" in captured[0]

    events = store.decision_events_for_hunt("hunt-1")
    target_events = [e for e in events if e.kind == "target_select"]
    assert len(target_events) == 1
    assert target_events[0].data["status"] == "selected"
    assert target_events[0].data["ordered_targets"]  # full factor breakdown recorded
    recall_id = store._conn.execute(
        "SELECT recall_id FROM recall_receipts WHERE hunt_id='hunt-1'"
    ).fetchone()["recall_id"]
    impacts = store.decision_impacts_for_recall(recall_id)
    assert len(impacts) == 5
    assert {impact["explanation"].split(" for ")[1].split(";")[0] for impact in impacts} == {
        "semantic_hunt_memory",
        "known_state",
        "roi_target_intelligence",
        "fleet_local_fine_tune",
        "playbook_memory",
    }


def test_recall_influenced_target_selection_changes_the_chosen_scenario(store, organ, monkeypatch):
    """R1: a live hunt where the recall receipt's selected context names a
    non-default cell, and that changes which cell TGT picks -- proving
    recall actually influences the decision, not just cosmetically present."""
    _make_hunt(store)

    from portal.modules.security.core.bully.organ import Organ as OrganCls

    # Two equal-prior candidate cells, tied on cost/priority except for
    # recall influence -- deterministic tie-break would pick "cell-a"
    # (lexicographically first) with no recall; injecting a recall receipt
    # whose selected_context names "cell-b" must flip the pick to "cell-b".
    candidate_cells = [
        {"cell_id": "cell-a", "subject": "cell-a", "scenario": "kerberoast_to_da", "prior": 0.5},
        {"cell_id": "cell-b", "subject": "cell-b", "scenario": "kerberoast_to_da", "prior": 0.5},
    ]

    def _recall_toward_b(self, *, hunt_id, query, k=8, filters=None):
        from portal.modules.security.core.bully.contracts import RecallReceipt

        receipt = RecallReceipt(
            recall_id="rr-forced",
            hunt_id=hunt_id,
            query=query,
            filters={},
            source_health={"embed": "ok"},
            projection_version=self.projection_version,
            embedding_version=self.embedding_version,
            reranker_version=None,
            candidates=[],
            exclusions=[],
            selected_context=[{"record": {"subject": "cell-b"}}],
        )
        self.store.recall_receipt_put(receipt)
        return receipt

    monkeypatch.setattr(OrganCls, "recall", _recall_toward_b)

    captured = []

    def _driver(target_cell, *, dry_run):
        captured.append(target_cell)
        return _proven_episode("kerberoast_to_da")

    orch.run_hunt_iteration(
        store,
        organ,
        hunt_id="hunt-1",
        actor="operator:alice",
        neighborhood="lab-default",
        target_cell={"candidate_cells": candidate_cells},
        lab_driver=_driver,
        investigation_arm=_fake_investigation_arm,
    )

    events = store.decision_events_for_hunt("hunt-1")
    target_event = next(e for e in events if e.kind == "target_select")
    assert target_event.data["selected_cell_id"] == "cell-b"
    assert "cell-b" in target_event.data["recall_influence"]["influenced_cells"]


def test_cost_blocked_unrankable_case_is_an_honest_block_with_recorded_reasons(store, organ):
    """R1: a candidate cell whose cost_ref was never metered/pre-flighted
    is declined MISSING_COST, and when it is the *only* eligible cell the
    whole iteration is an honest BLOCKED stop -- never a fabricated
    zero-cost selection."""
    _make_hunt(store)
    candidate_cells = [
        {
            "cell_id": "cell-unmeasured",
            "subject": "cell-unmeasured",
            "scenario": "kerberoast_to_da",
            "cost_ref": "never-metered-family",
            "prior": 0.9,
        }
    ]

    driver_called = []

    def _driver(target_cell, *, dry_run):
        driver_called.append(True)
        return _proven_episode("kerberoast_to_da")

    with pytest.raises(orch.HonestBlockedError):
        orch.run_hunt_iteration(
            store,
            organ,
            hunt_id="hunt-1",
            actor="operator:alice",
            neighborhood="lab-default",
            target_cell={"candidate_cells": candidate_cells},
            lab_driver=_driver,
            investigation_arm=_fake_investigation_arm,
        )

    assert driver_called == []  # never reached the lab
    row = store.hunt_get("hunt-1")
    assert row["stage"] == "BLOCKED"

    events = store.decision_events_for_hunt("hunt-1")
    target_event = next(e for e in events if e.kind == "target_select")
    assert target_event.data["status"] == "unrankable"
    declined = target_event.data["declined"]
    assert len(declined) == 1
    assert declined[0]["reason"] == "MISSING_COST"
    assert declined[0]["cell_id"] == "cell-unmeasured"
