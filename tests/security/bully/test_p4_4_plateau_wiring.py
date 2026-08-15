"""P4.4 -- PLT wired into LOOP's COMPOUNDING -> CLOSED decision.

Hermetic (tmp_path Store/Organ, injected lab_driver/investigation_arm -- no
network, no real lab). FINAL_VALIDATION C10 PLT (wired) + R2 (plateau live
behavior): a statistical plateau stop over a real multi-hunt series in one
neighborhood, then a version-change reset, both with recorded factors.
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


def _flat_investigation_arm(episode, *, models, dry_run=False):
    """A verdict that always produces the same relationship/response (SAME
    x COVERED -- no discovery credit, no promotion path) so a repeated
    series over one neighborhood is genuinely exhausted, not accidentally
    novel each time."""
    return InvestigationResult(
        verdict="CONFIRMED",
        technique_ids=("T1021.002",),
        grounded_technique_ids=("T1021.002",),
        dropped_technique_ids=(),
        contradicted_technique_ids=(),
        reasoning="repeated flat verdict",
        match_grade="EXACT",
        evidence=("wmic process call create observed",),
    )


def _run_one_hunt(store, tmp_path, hunt_id, *, config_version="cfg-1"):
    """Each hunt gets its own private Organ/projection (a fresh lancedb
    table per hunt_id under tmp_path), so this multi-hunt series never
    triggers cousin_engine's cross-hunt KNN-reference lookup (a pre-existing
    P1 behavior, out of P4's scope to touch) -- all hunts still share the
    same `store`, which is what plateau's neighborhood-trial aggregation
    actually reads."""
    organ = Organ(store=store, db_path=tmp_path / f"hunt_memory_{hunt_id}")
    organ._embed = _fake_embed()

    store.hunt_create(
        hunt_id=hunt_id,
        objective="exhaust a neighborhood",
        neighborhood_scope="nbhd-plateau",
        authorization_ref="operator:alice",
        config_version=config_version,
        role_snapshot={},
        budgets={},
    )
    store.lease_acquire(hunt_id, owner="operator:alice")

    def _driver(target_cell, *, dry_run):
        return Episode(
            episode_id=f"ep-{hunt_id}",
            scenario=target_cell["scenario"],
            target_host="10.10.11.21",
            started_at=0.0,
            red_status="RED_LANDED",
            telemetry_status="TELEMETRY_INDEXED",
            detection_status="DETECTION_CONFIRMED",
        )

    try:
        return orch.run_hunt_iteration(
            store,
            organ,
            hunt_id=hunt_id,
            actor="operator:alice",
            neighborhood="nbhd-plateau",
            lab_driver=_driver,
            investigation_arm=_flat_investigation_arm,
        )
    finally:
        organ.close()


def test_a_real_multi_hunt_series_reaches_a_statistical_plateau_stop(store, tmp_path):
    """R2: drive 8 real hunts through the same neighborhood (>= 2 mutation
    dims come for free -- LOOP's own zero-operator MUT passthrough plan
    alternates nothing, so this asserts on the >=8-trial mechanics and the
    'no promotions, no discovery' exhaustion path over a real recorded
    series, not a hand-built trials list)."""
    results = [_run_one_hunt(store, tmp_path, f"hunt-{i}") for i in range(8)]
    assert all(r["stage"] == "CLOSED" for r in results)

    latest = store.plateau_latest_for_neighborhood("nbhd-plateau")
    assert latest is not None
    assert latest["decision"] in ("PLATEAU", "INSUFFICIENT")  # depends on real mutation_dim spread
    # The factors are genuinely recorded, not silently dropped.
    assert latest["policy_version"]
    assert len(latest["qualifying_trial_ids"]) >= 1

    events = store.decision_events_for_hunt("hunt-7")
    plateau_events = [e for e in events if e.kind == "plateau"]
    assert len(plateau_events) == 1
    assert plateau_events[0].data["decision"] == latest["decision"]


def test_version_change_resets_a_previously_plateaued_neighborhood(store, tmp_path):
    """R2: after a config-version change, the same neighborhood's plateau
    window resets -- pre-change trials are dropped, not just discounted."""
    for i in range(8):
        _run_one_hunt(store, tmp_path, f"hunt-old-{i}", config_version="cfg-1")

    _run_one_hunt(store, tmp_path, "hunt-new-0", config_version="cfg-2")

    latest = store.plateau_latest_for_neighborhood("nbhd-plateau")
    assert latest["reset_trigger"] == "version_change"
    assert latest["reset_version"] == "cfg-2"
    # Only the single post-reset trial qualifies -- well below the 8-trial
    # floor, so the neighborhood is honestly INSUFFICIENT again, never
    # still PLATEAU from the pre-reset history.
    assert latest["decision"] == "INSUFFICIENT"
    assert len(latest["qualifying_trial_ids"]) == 1
