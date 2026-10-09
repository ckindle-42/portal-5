#!/usr/bin/env python3
"""Defensive Bully TRAIN -- thin host-native CLI entry (P6.4, I-17).

All the real orchestration logic lives in
``portal.modules.security.core.bully.training``; this script only parses
args, opens the SUB store, resolves the base-model config alias from
``config/security/hunt.yaml::training`` (never a hardcoded model name,
MASTER SS5/SS11), and prints the resulting `TrainOutcome` as JSON.

Subcommands:
    build-dataset   HARV: harvest.build_dataset(role, window)
    release-dataset operator dataset release (separate from model promotion)
    run             TRAIN: training.run(role, dataset_version=...)
    serve           canary + atomic alias promotion (operator confirm)
    rollback        atomic alias re-point

Examples:
    python3 scripts/defensive_bully_train.py build-dataset --role hunter
    python3 scripts/defensive_bully_train.py release-dataset --dataset-version dv-... \\
        --operator operator:alice
    python3 scripts/defensive_bully_train.py run --role hunter \\
        --dataset-version dv-... --data-dir /path/to/train_jsonl_dir
    python3 scripts/defensive_bully_train.py serve --model-tag bully-... \\
        --operator operator:alice
    python3 scripts/defensive_bully_train.py rollback --role hunter \\
        --operator operator:alice --reason "canary regression"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully import config as bully_config  # noqa: E402
from portal.modules.security.core.bully import cutover, harvest, training  # noqa: E402
from portal.modules.security.core.bully.contracts import DecisionImpact, new_id  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402
from portal.modules.security.core.candidate_eval import _compute_delta  # noqa: E402


def _open_store() -> Store:
    return Store(bully_config.hunt_dir() / "hunt_state.db")


def _training_config() -> dict:
    return bully_config.load_hunt_config().get("training") or {}


def _incumbent_delta_pt(report_path: Path) -> float:
    """Derive the frozen general-bench regression leg from raw arm results.

    The candidate-eval aggregate's unique-coverage delta is expressed on a
    0..1 scale. TRAIN's acceptance contract is in percentage points, so the
    conversion is explicit here. We recompute from the two arms instead of
    trusting a precomputed ``deltas`` field in the report.
    """
    report = json.loads(report_path.read_text(encoding="utf-8"))
    candidate_results = report.get("candidate_results")
    incumbent_results = report.get("incumbent_results")
    if not isinstance(candidate_results, list) or not isinstance(incumbent_results, list):
        raise ValueError(
            "candidate-eval report must contain candidate_results and incumbent_results"
        )
    deltas = _compute_delta(candidate_results, incumbent_results)
    aggregate = next((row for row in deltas if row.get("scenario") == "__aggregate__"), None)
    if aggregate is None:
        raise ValueError("candidate-eval report has no comparable aggregate evidence")
    return round(float(aggregate["unique_coverage_delta"]) * 100.0, 3)


def cmd_build_dataset(args: argparse.Namespace) -> int:
    store = _open_store()
    try:
        cfg = _training_config()
        ref = harvest.build_dataset(
            store, args.role, {"since": args.since}, min_size=cfg.get("min_dataset_size", 20)
        )
        readiness = harvest.refinement_readiness(
            store, args.role, min_size=cfg.get("min_dataset_size", 20)
        )
        feed_mode = cutover.feed_mode(bully_config.load_hunt_config(), "training_pair_harvest")
        queue_id = (
            harvest.surface_refinement_readiness(store, readiness)
            if feed_mode == "authoritative"
            else None
        )
        ref["refinement_readiness"] = readiness.as_dict()
        ref["readiness_queue_id"] = queue_id
        ref["feed_mode"] = feed_mode
    finally:
        store.close()
    print(json.dumps(ref, indent=2, sort_keys=True, default=str))
    return 0 if ref.get("built") else 1


def cmd_release_dataset(args: argparse.Namespace) -> int:
    store = _open_store()
    try:
        before = store.dataset_version_get(args.dataset_version)
        store.dataset_version_release(
            args.dataset_version, operator_actor=args.operator, approval_ref=args.approval_ref
        )
        row = store.dataset_version_get(args.dataset_version)
        recall_id = store.latest_recall_id()
        mode = cutover.feed_mode(bully_config.load_hunt_config(), "training_pair_harvest")
        if recall_id is not None:
            store.decision_impact_put(
                DecisionImpact(
                    impact_id=new_id("impact"),
                    recall_id=recall_id,
                    consuming_decision_ref=args.dataset_version,
                    before={
                        "dataset_version": args.dataset_version,
                        "status": before["status"] if before else None,
                    },
                    after={
                        "dataset_version": args.dataset_version,
                        "status": row["status"] if row else None,
                    },
                    cited_record_ids=[args.dataset_version],
                    change_kind="CONTROL_ADDED",
                    explanation=(
                        "P7 paired cutover proof for training_pair_harvest; "
                        f"mode={mode}; released corpus became eligible for later TRAIN consumption"
                    ),
                )
            )
    finally:
        store.close()
    print(json.dumps(row, indent=2, sort_keys=True, default=str))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    store = _open_store()
    try:
        feed_mode = cutover.feed_mode(bully_config.load_hunt_config(), "training_pair_harvest")
        if feed_mode != "authoritative":
            print(
                "TRAIN refused: training_pair_harvest consumption is not authoritative "
                f"(mode={feed_mode})",
                file=sys.stderr,
            )
            return 3
        cfg = _training_config()
        base_model = args.base_model or (cfg.get("base_models") or {}).get(args.role)
        if not base_model:
            print(
                f"no base model configured for role={args.role!r} -- set "
                f"config/security/hunt.yaml::training.base_models.{args.role} "
                "or pass --base-model",
                file=sys.stderr,
            )
            return 2
        try:
            incumbent_delta_pt = _incumbent_delta_pt(Path(args.candidate_eval_report))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"invalid candidate-eval evidence: {exc}", file=sys.stderr)
            return 2
        lora_cfg = cfg.get("lora") or {}
        outcome = training.run(
            store,
            args.role,
            dataset_version=args.dataset_version,
            base_model=base_model,
            train_data_dir=Path(args.data_dir),
            quant=cfg.get("quant", "Q4_K_M"),
            lora_iters=args.iters or lora_cfg.get("iters", 200),
            lora_batch_size=args.batch_size or lora_cfg.get("batch_size", 4),
            lora_num_layers=args.num_layers or lora_cfg.get("num_layers", 8),
            seed=args.seed,
            incumbent_delta_pt=incumbent_delta_pt,
        )
    except (training.TrainingBlockedError, training.ToolchainMissingError) as exc:
        print(f"TRAIN refused: {exc}", file=sys.stderr)
        return 3
    finally:
        store.close()
    print(json.dumps(outcome, indent=2, sort_keys=True, default=str))
    return 0 if outcome.get("passed") else 1


def cmd_serve(args: argparse.Namespace) -> int:
    store = _open_store()
    try:
        outcome = training.serve(store, args.model_tag, operator_actor=args.operator)
    finally:
        store.close()
    print(json.dumps(outcome, indent=2, sort_keys=True, default=str))
    return 0 if outcome.get("verdict") == "served" else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    store = _open_store()
    try:
        outcome = training.rollback(
            store, args.role, operator_actor=args.operator, reason=args.reason
        )
    finally:
        store.close()
    print(json.dumps(outcome, indent=2, sort_keys=True, default=str))
    return 0 if outcome.get("rolled_back_to") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="defensive_bully_train", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build-dataset")
    p.add_argument(
        "--role", required=True, choices=("hunter", "analyst", "disprover", "cousin_smeller")
    )
    p.add_argument("--since", type=float, default=0.0)
    p.set_defaults(func=cmd_build_dataset)

    p = sub.add_parser("release-dataset")
    p.add_argument("--dataset-version", required=True)
    p.add_argument("--operator", required=True, help="operator:<id>")
    p.add_argument("--approval-ref", required=True)
    p.set_defaults(func=cmd_release_dataset)

    p = sub.add_parser("run")
    p.add_argument("--role", required=True, choices=tuple(bully_config.REFINEMENT_ROLE_MAP))
    p.add_argument("--dataset-version", required=True)
    p.add_argument("--data-dir", required=True, help="directory with train.jsonl/valid.jsonl")
    p.add_argument(
        "--candidate-eval-report",
        required=True,
        help="general security candidate-eval JSON containing candidate and incumbent arms",
    )
    p.add_argument(
        "--base-model", default=None, help="override the config-resolved base model alias"
    )
    p.add_argument("--iters", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--num-layers", type=int, default=None)
    p.add_argument("--seed", type=int, default=1234)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve")
    p.add_argument("--model-tag", required=True)
    p.add_argument("--operator", required=True, help="operator:<id>")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("rollback")
    p.add_argument(
        "--role", required=True, choices=("hunter", "analyst", "disprover", "cousin_smeller")
    )
    p.add_argument("--operator", required=True, help="operator:<id>")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_rollback)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
