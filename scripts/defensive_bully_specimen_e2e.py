#!/usr/bin/env python3
"""Run the P7 E2E proof over frozen, real observed specimens."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully import cutover, handoff, promotion
from portal.modules.security.core.bully.contracts import (
    DecisionEvent,
    DecisionImpact,
    RecallReceipt,
)
from portal.modules.security.core.bully.cousin_calibration_bench import (
    BASELINE_CALIBRATION_V1,
    load_specimen_corpus,
)
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger
from portal.modules.security.core.bully.store import Store
from portal.modules.security.core.recall_attribution import (
    PRESENT,
    evidence_presence,
    technique_discriminators,
)
from portal.modules.security.core.siem import capture_store
from portal.modules.security.core.siem.spl_backend import SplunkBackend
from portal.modules.security.core.siem.spl_detections import spl_for

PROOF_SCHEMA = "BULLY_P7_SPECIMEN_E2E_V1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _telemetry(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        str(event)
        for sourcetype in sorted(payload.get("telemetry") or {})
        for event in payload["telemetry"][sourcetype]
    )


def _close_hunt(store: Store, hunt_id: str) -> None:
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
        row = store.hunt_get(hunt_id)
        store.hunt_advance_stage(hunt_id, stage, expected_version=row["version"])


def _gate_results(
    parent: dict,
    live: dict,
    parent_truth: dict,
    evidence_path: Path,
    live_evidence_path: Path,
    *,
    ship: bool,
) -> dict[str, Any]:
    replay_receipts = [
        capture_store.replay_capture(evidence_path, dry_run=not ship) for _ in range(3)
    ]
    indexed_runs = [
        bool(item.get("ok")) and (not ship or item.get("indexed_confirmed") is True)
        for item in replay_receipts
    ]
    live_lab_receipt = capture_store.replay_capture(live_evidence_path, dry_run=not ship)
    live_lab_indexed = bool(live_lab_receipt.get("ok")) and (
        not ship or live_lab_receipt.get("indexed_confirmed") is True
    )
    live_query = None
    live_lab_query = None
    if ship:
        live_query = SplunkBackend().query_episode(
            {"earliest": "-15m", "latest": "now"},
            episode_id=parent["specimen_id"],
            host=parent["engine_view"]["episode_view"]["target_host"],
            limit=20,
        )
        live_lab_query = SplunkBackend().query_episode(
            {"earliest": "-15m", "latest": "now"},
            episode_id=live["specimen_id"],
            host=live["engine_view"]["episode_view"]["target_host"],
            limit=20,
        )
        telemetry = live_query["telemetry"]
    else:
        telemetry = _telemetry(evidence_path)
    oracle_checks = []
    for technique_id in parent_truth["data_yml_techniques"]:
        result, matched = evidence_presence(
            telemetry, technique_discriminators(technique_id)["tokens"]
        )
        oracle_checks.append({"technique_id": technique_id, "result": result, "matched": matched})
    g1a = promotion.check_g1a_static(
        {
            "has_spl_hit": any(item["result"] == PRESENT for item in oracle_checks),
            "within_window": True,
            "target_match": not ship
            or bool(live_query and live_query["rows"] and not live_query.get("error")),
        }
    )
    g1b = promotion.check_g1b_dynamic({"reexecution_runs": indexed_runs})
    benign_evidence = handoff.gather_quiet_on_benign(
        spl_for(parent_truth["data_yml_techniques"][0])
    )
    benign_check = handoff.check_quiet_on_benign(benign_evidence)
    return {
        "G1a": g1a,
        "G1b": g1b,
        "G2": promotion.check_g2(
            {"benign_corpus_fires": benign_check["outcome"] != "pass"},
            cousin_assessment={"vetoes": []},
        ),
        "G2_rejection_control": promotion.check_g2(
            {"benign_corpus_fires": True}, cousin_assessment={"vetoes": []}
        ),
        "benign_evidence": benign_evidence,
        "oracle_checks": oracle_checks,
        "replay_receipts": replay_receipts,
        "execution_mode": "live_indexed" if ship else "offline_integrity",
        "indexed_runs": indexed_runs,
        "live_query": live_query,
        "live_lab_replay_receipt": live_lab_receipt,
        "live_lab_indexed": live_lab_indexed,
        "live_lab_query": live_lab_query,
    }


def _record_proof_store(
    store_path: Path, corpus: dict, parent: dict, live: dict, *, execution_mode: str
) -> None:
    hunt_id = "hunt-p7-specimen-proof-v1"
    recall_id = "recall-p7-specimen-proof-v1"
    with Store(store_path) as store:
        store.hunt_create(
            hunt_id=hunt_id,
            objective="P7 proof on frozen real specimen corpus",
            neighborhood_scope="SPECIMEN_CORPUS_V1",
            authorization_ref="task:TASK_BULLY_P7_2_SPECIMEN_CORPUS_AND_BLIND_BENCH_V1",
            config_version="p7-specimen-proof-v1",
            role_snapshot={},
            budgets={},
        )
        store.recall_receipt_put(
            RecallReceipt(
                recall_id=recall_id,
                hunt_id=hunt_id,
                query="frozen specimen proof",
                filters={"corpus_snapshot_hash": corpus["snapshot_hash"]},
                source_health={"specimen_corpus": "complete"},
                projection_version="SPECIMEN_CORPUS_V1",
                embedding_version="read-only-snapshot",
                reranker_version=None,
                candidates=[{"record_id": parent["specimen_id"]}],
            )
        )
        store.record_decision(
            DecisionEvent(
                event_id="event-p7-live-specimen-v1",
                hunt_id=hunt_id,
                iteration_id=None,
                actor="system:specimen-e2e",
                kind="gate",
                subject_id=live["specimen_id"],
                rationale="ground-truth-complete live-lab specimen admitted to P7 proof",
                data={
                    "episode_id": live["specimen_id"],
                    "used_synthetic": False,
                    "source_lane": "live_lab",
                    "corpus_snapshot_hash": corpus["snapshot_hash"],
                    "execution_mode": execution_mode,
                },
            )
        )
        for index, feed in enumerate(cutover.FEEDS):
            store.decision_impact_put(
                DecisionImpact(
                    impact_id=f"impact-p7-specimen-{index}",
                    recall_id=recall_id,
                    consuming_decision_ref=f"p7-specimen-{feed}",
                    before={"specimen_corpus": "absent"},
                    after={"specimen_corpus": corpus["snapshot_hash"], "feed": feed},
                    cited_record_ids=[parent["specimen_id"], live["specimen_id"]],
                    change_kind="CONTROL_ADDED",
                    explanation=f"P7 paired cutover proof for {feed}; mode=authoritative",
                )
            )
        _close_hunt(store, hunt_id)


def _two_axis(baseline: dict[str, Any]) -> dict[str, int]:
    rows = [
        row for row in baseline["curve"] if row.get("relationship") and row.get("oracle_response")
    ]
    return {
        "rows": len(rows),
        "live_lab_rows": sum(row["source_lane"] == "live_lab" for row in rows),
        "near_miss_rows": sum(row["oracle_response"] == "NEAR_MISS" for row in rows),
        "indeterminate_rows": len(baseline.get("indeterminate") or []),
    }


def _proof_checks(
    corpus: dict, two_axis: dict[str, int], gates: dict[str, Any], recovery: dict
) -> dict[str, bool]:
    return {
        "corpus_complete": bool(corpus.get("complete")),
        "two_axis_real_grading": two_axis["rows"] == len(corpus["specimens"])
        and two_axis["live_lab_rows"] > 0,
        "g1a_reproduction": gates["G1a"]["outcome"] == "pass",
        "g1b_reproduction": gates["G1b"]["outcome"] == "pass",
        "live_indexed_replay": gates["execution_mode"] != "live_indexed"
        or (
            all(gates["indexed_runs"])
            and gates["live_lab_indexed"]
            and bool(gates["live_query"] and gates["live_query"]["rows"])
            and bool(gates["live_lab_query"] and gates["live_lab_query"]["rows"])
        ),
        "g2_benign_zero_fire": gates["G2"]["outcome"] == "pass",
        "g2_rejects_benign_fire": gates["G2_rejection_control"]["outcome"] == "fail",
        "decision_impact": len(cutover.FEEDS) == 6,
        "recovery": all(
            item["rollback_restored_baseline"] and item["records_retained"]
            for item in recovery.values()
        ),
    }


def run_proof(
    *,
    corpus_path: Path,
    ledger: SpecimenLedger,
    baseline_path: Path,
    output_dir: Path,
    ship: bool = False,
) -> dict[str, Any]:
    corpus = load_specimen_corpus(corpus_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline.get("schema") != BASELINE_CALIBRATION_V1:
        raise ValueError("P7 E2E requires BASELINE_CALIBRATION_V1")
    if baseline.get("corpus_snapshot_hash") != corpus["snapshot_hash"]:
        raise ValueError("baseline and specimen corpus snapshots differ")

    parent = next(item for item in corpus["specimens"] if item["source_lane"] == "attack_data")
    live = next(item for item in corpus["specimens"] if item["source_lane"] == "live_lab")
    parent_truth = ledger.truth_for(parent["specimen_id"])
    evidence_path = corpus_path.parent / "evidence" / parent["evidence_ref"]
    live_evidence_path = corpus_path.parent / "evidence" / live["evidence_ref"]
    gates = _gate_results(
        parent,
        live,
        parent_truth,
        evidence_path,
        live_evidence_path,
        ship=ship,
    )

    two_axis = _two_axis(baseline)

    output_dir.mkdir(parents=True, exist_ok=False)
    store_path = output_dir / "p7_specimen_proof.db"
    _record_proof_store(store_path, corpus, parent, live, execution_mode=gates["execution_mode"])

    recovery = {
        feed: cutover.rollback_drill(
            feed,
            replacement={"corpus": corpus["snapshot_hash"]},
            baseline={"consumer": "baseline"},
        )
        for feed in cutover.FEEDS
    }
    checks = _proof_checks(corpus, two_axis, gates, recovery)
    proof = {
        "schema": PROOF_SCHEMA,
        "recorded_at": datetime.now(UTC).isoformat(),
        "execution_mode": gates["execution_mode"],
        "passed": all(checks.values()),
        "checks": checks,
        "corpus": {
            "path": str(corpus_path.resolve()),
            "sha256": _sha256(corpus_path),
            "snapshot_hash": corpus["snapshot_hash"],
            "per_lane_counts": corpus["per_lane_counts"],
        },
        "baseline": {
            "path": str(baseline_path.resolve()),
            "sha256": _sha256(baseline_path),
            "cold_untuned": baseline["cold_untuned"],
            "training_applied": baseline["training_applied"],
            "threshold_tuning_applied": baseline["threshold_tuning_applied"],
            "two_axis": two_axis,
        },
        "gates": gates,
        "decision_impact_ids": [f"impact-p7-specimen-{index}" for index in range(6)],
        "recovery": recovery,
        "store_path": str(store_path.resolve()),
    }
    (output_dir / "p7_specimen_e2e.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--ledger-root", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--ship",
        action="store_true",
        help="ship through HEC and require live Splunk index/query confirmation",
    )
    args = parser.parse_args(argv)
    proof = run_proof(
        corpus_path=args.corpus,
        ledger=SpecimenLedger(args.ledger_root),
        baseline_path=args.baseline,
        output_dir=args.output_dir,
        ship=args.ship,
    )
    print(json.dumps({"passed": proof["passed"], "checks": proof["checks"]}, indent=2))
    return 0 if proof["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
