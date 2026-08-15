"""P7/M6 six-feed cutover, disagreement, and rollback proofs."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from portal.modules.security.core.bully import config, cutover
from portal.modules.security.core.bully import orchestrator as orch
from portal.modules.security.core.bully.contracts import (
    DecisionEvent,
    DecisionImpact,
    RecallReceipt,
)
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store
from scripts import defensive_bully_closeout, defensive_bully_train

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_all_six_feeds_are_cut_over_to_authoritative():
    cfg = config.load_hunt_config()
    assert set(cutover.FEEDS) == set(cfg["feeds"])
    assert {cutover.feed_mode(cfg, feed) for feed in cutover.FEEDS} == {"authoritative"}


def test_shadow_records_disagreement_but_preserves_baseline_result():
    result = cutover.consume(
        "semantic_hunt_memory",
        "shadow",
        baseline={"selected": "cell-a"},
        replacement={"selected": "cell-b"},
    )
    assert result.disagreed is True
    assert result.effective == {"selected": "cell-a"}
    assert result.replacement == {"selected": "cell-b"}


def test_each_authoritative_feed_has_a_byte_stable_rollback_drill():
    for feed in cutover.FEEDS:
        proof = cutover.rollback_drill(
            feed,
            replacement={"feed": feed, "decision": "new"},
            baseline={"feed": feed, "decision": "legacy"},
        )
        assert proof == {
            "feed": feed,
            "authoritative_used_replacement": True,
            "rollback_restored_baseline": True,
            "records_retained": True,
        }


def test_dataset_readiness_is_not_a_seventh_feed():
    assert "dataset_readiness" not in cutover.FEEDS
    assert len(cutover.FEEDS) == 6


def test_released_harvest_dataset_records_the_sixth_feed_impact(tmp_path, monkeypatch, capsys):
    db = tmp_path / "hunt_state.db"
    with Store(db) as store:
        store.hunt_create(
            hunt_id="hunt-source",
            objective="source a later refinement",
            neighborhood_scope="lab",
            authorization_ref="operator:test",
            config_version="cfg",
            role_snapshot={},
            budgets={},
        )
        store.recall_receipt_put(
            RecallReceipt(
                recall_id="rr-source",
                hunt_id="hunt-source",
                query="prior hunt facts",
                filters={},
                source_health={"organ": "ok"},
                projection_version="v1",
                embedding_version="v1",
                reranker_version=None,
            )
        )
        store.dataset_version_put(
            dataset_version="dv-proof",
            role="analyst",
            window={"since": 0},
            counts={"total": 20},
            split_manifest={"train": 14, "val": 4, "test": 2},
            dedup_leakage_report={"quarantined_total": 0},
            replay_mix_sources=[],
            manifest_path=None,
        )

    monkeypatch.setattr(defensive_bully_train, "_open_store", lambda: Store(db))
    rc = defensive_bully_train.cmd_release_dataset(
        SimpleNamespace(
            dataset_version="dv-proof",
            operator="operator:test",
            approval_ref="approval:p7",
        )
    )
    capsys.readouterr()
    assert rc == 0

    with Store(db) as store:
        impacts = store.decision_impacts_for_recall("rr-source")
        assert len(impacts) == 1
        assert "training_pair_harvest" in impacts[0]["explanation"]
        assert impacts[0]["before"]["status"] == "built"
        assert impacts[0]["after"]["status"] == "released"
        assert impacts[0]["change_kind"] == "CONTROL_ADDED"


def test_closeout_bundle_passes_only_with_all_six_effects(tmp_path):
    db = tmp_path / "hunt_state.db"
    with Store(db) as store:
        store.hunt_create(
            hunt_id="hunt-proof",
            objective="paired feed proof",
            neighborhood_scope="lab",
            authorization_ref="operator:test",
            config_version="cfg",
            role_snapshot={},
            budgets={},
        )
        store.recall_receipt_put(
            RecallReceipt(
                recall_id="rr-proof",
                hunt_id="hunt-proof",
                query="proof",
                filters={},
                source_health={"organ": "ok"},
                projection_version="v1",
                embedding_version="v1",
                reranker_version=None,
            )
        )
        store.record_decision(
            DecisionEvent(
                event_id="event-live",
                hunt_id="hunt-proof",
                iteration_id=None,
                actor="system:test",
                kind="gate",
                subject_id="episode-live",
                rationale="truth-plane episode",
                data={"episode_id": "episode-live", "used_synthetic": False},
            )
        )
        for stage in (
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
            row = store.hunt_get("hunt-proof")
            store.hunt_advance_stage("hunt-proof", stage, expected_version=row["version"])
        for index, feed in enumerate(cutover.FEEDS):
            store.decision_impact_put(
                DecisionImpact(
                    impact_id=f"impact-{index}",
                    recall_id="rr-proof",
                    consuming_decision_ref=f"decision-{index}",
                    before={"choice": "a"},
                    after={"choice": "b"},
                    cited_record_ids=[f"source-{index}"],
                    change_kind="CONTROL_ADDED",
                    explanation=f"P7 paired cutover proof for {feed}; mode=authoritative",
                )
            )

    calibration = tmp_path / "calibration.json"
    calibration.write_text('{"passed": false, "calibration_proposal": {"version": "v2"}}')
    refinement = tmp_path / "verdict.json"
    refinement.write_text('{"verdict": "declined_no_gain"}')
    validation = tmp_path / "validation.json"
    validation.write_text('{"passed": true}')
    bundle = defensive_bully_closeout.assemble(
        store_path=db,
        calibration_report=calibration,
        refinement_verdict=refinement,
        validation_summary=validation,
        validation_logs=[],
    )
    assert bundle["release_acceptance"]["status"] == "PASS"
    assert bundle["rollback_all_passed"] is True
    assert {proof["status"] for proof in bundle["feeds"].values()} == {"PASS"}


def test_unexpected_live_driver_failure_blocks_and_releases_the_hunt(tmp_path, monkeypatch):
    store = Store(tmp_path / "hunt_state.db")
    organ = Organ(store=store, db_path=tmp_path / "hunt_memory")
    organ._embed = lambda texts: [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(orch, "_resolve_live_investigation_models", lambda _store: {})

    def fail_driver(_target, *, dry_run):
        raise RuntimeError("injected lab failure")

    with pytest.raises(RuntimeError, match="injected lab failure"):
        orch.run_hunt(
            actor="operator:test",
            store=store,
            organ=organ,
            lab_driver=fail_driver,
        )

    hunt = store.hunts()[0]
    assert hunt["stage"] == "BLOCKED"
    store.lease_acquire(hunt["hunt_id"], owner="operator:recovery")
    organ.close()
    store.close()


def test_coverage_cells_persist_across_restart_without_cold_rebuild(tmp_path):
    db = tmp_path / "hunt_state.db"
    with Store(db) as store:
        assert store.coverage_cell_put(
            {
                "cell_id": "cell:one",
                "subject": "T1190",
                "scenario": "web_sqli_dump",
                "prior": 0.5,
            }
        )
        assert not store.coverage_cell_put(
            {
                "cell_id": "cell:one",
                "subject": "T1190",
                "scenario": "web_sqli_dump",
                "prior": 0.5,
            }
        )
    with Store(db) as reopened:
        cells = reopened.coverage_cells()
        assert len(cells) == 1
        assert cells[0]["cell_id"] == "cell:one"
        assert cells[0]["persistence"]["version"] == 1


def test_authoritative_loop_has_no_legacy_hunting_driver_imports():
    path = REPO_ROOT / "portal/modules/security/core/bully/orchestrator.py"
    tree = ast.parse(path.read_text())
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(
        name.endswith(("growth_loop", "continuous_eval", "capability_graph")) for name in imported
    )
    assert "coverage_cell_put" in path.read_text()


def test_growth_loop_has_no_remaining_production_caller():
    core = REPO_ROOT / "portal/modules/security/core"
    callers = []
    for path in core.rglob("*.py"):
        if path.name == "growth_loop.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("growth_loop")
            ):
                callers.append(str(path.relative_to(REPO_ROOT)))
    assert callers == []


def test_episode_name_collision_is_reconciled_as_bench_only():
    text = (REPO_ROOT / "portal/modules/security/core/agentic_blue_eval.py").read_text()
    assert "Legacy acceptance-bench episode" in text
    assert "core.episode.Episode" in text
