"""P3.2/P3.4 -- BR-DRIFT wired into LOOP's ANALYZING stage.

Hermetic (tmp_path Store/Organ, injected lab_driver/investigation_arm -- no
network, no real lab). FINAL_VALIDATION C6 (drift engine wired into the real
loop, flags + baselines persisted every iteration).
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


def test_drift_engine_records_insufficient_baseline_on_first_episode(store, organ):
    _make_hunt(store)

    def _driver(target_cell, *, dry_run):
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

    assert len(result["drift_flags"]) == 1
    assert result["drift_flags"][0]["status"] == "INSUFFICIENT_BASELINE"
    n_flags = store._conn.execute("SELECT COUNT(*) AS n FROM drift_flags").fetchone()["n"]
    assert n_flags == 1
    n_baselines = store._conn.execute("SELECT COUNT(*) AS n FROM detection_baselines").fetchone()[
        "n"
    ]
    assert n_baselines == 1
    baseline = store._conn.execute("SELECT * FROM detection_baselines LIMIT 1").fetchone()
    assert baseline["sample_count"] == 1
    assert baseline["status"] == "warmup"
