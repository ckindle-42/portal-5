"""R.4 -- the cutover: orchestrator grades through the reintegrated loop_grader,
not cousin_engine.grade (R1: no parallel grader survives)."""

from __future__ import annotations

import ast
from pathlib import Path

from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.investigation import InvestigationResult
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.episode import Episode

_ORCHESTRATOR_PATH = (
    Path(__file__).parents[3]
    / "portal"
    / "modules"
    / "security"
    / "core"
    / "bully"
    / "orchestrator.py"
)


def _fake_embed(dim: int = 8):
    def _embed(texts):
        return [[float((hash(t) >> i) % 7) for i in range(dim)] for t in texts]

    return _embed


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


def test_import_scan_cousin_engine_grade_is_not_on_the_call_path() -> None:
    """Seeded violation guard: cousin_engine.grade must not be imported by
    orchestrator.py -- the whole point of R.4 is that there is one grader."""
    tree = ast.parse(_ORCHESTRATOR_PATH.read_text())
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("cousin_engine")
        ):
            imported_names.update(alias.name for alias in node.names)
    assert "grade" not in imported_names


def test_analyzing_emits_assessment_via_loop_grader(tmp_path) -> None:
    store = Store(tmp_path / "hunt_state.db")
    organ = Organ(store=store, db_path=tmp_path / "hunt_memory")
    organ._embed = _fake_embed()
    try:
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

        row = store._conn.execute(
            "SELECT explanation FROM cousin_assessments ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        import json

        explanation = json.loads(row["explanation"])
        assert explanation["grader"] == "loop-grader-v1"
        assert "match_level" in explanation
    finally:
        organ.close()
        store.close()
