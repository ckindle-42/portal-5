#!/usr/bin/env python3
"""T2 of TASK_BULLY_V3_THRESHOLD_VALIDATION_V1 -- frozen P6.8 cousin-calibration sweep on the
thresholds that stand (cousin_engine.DEFAULT_THRESHOLDS, bully-cousin-thresholds-v3).

Builds a fresh, isolated Organ snapshot holding only the four CALIB_PARENTS_V1 reference records
(children are never indexed), runs cousin_calibration_bench.run_bench against it, and writes the
full artifacts (curve CSV/SVG, calibration_report.json, per-child rows) to --scratch. Only the
summary (pass/fail, failure-class counts, thresholds, parent snapshot hash) goes to --out.

Usage:
    uv run python scripts/bully_v3_t2_calibration.py \
        --scratch /Volumes/data01/portal5_hunt/artifacts/calibration/T2_V3_<stamp> \
        --out reports/bully_calibration/<stamp>_v3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ruff: noqa: E402

from portal.modules.security.core.bully import cousin_calibration_bench as bench
from portal.modules.security.core.bully import cousin_engine
from portal.modules.security.core.bully.organ import Organ
from portal.modules.security.core.bully.store import Store

EMBED_VERSION = "google/embeddinggemma-2:768d:sentence-similarity"


def _summarise(report: Any, scratch: Path) -> dict[str, Any]:
    raw = json.loads((scratch / "calibration_report.json").read_text(encoding="utf-8"))
    failures = {k: len(v) for k, v in (raw.get("failures") or {}).items()}
    return {
        "schema": "BULLY_V3_T2_CALIBRATION_V1",
        "policy_version": raw["policy_version"],
        "sweep_version": raw["sweep_version"],
        "parent_set_version": raw["parent_set_version"],
        "parent_snapshot_hash": raw["parent_snapshot_hash"],
        "thresholds_version": raw["thresholds_version"],
        "thresholds": dict(cousin_engine.DEFAULT_THRESHOLDS),
        "weights": dict(cousin_engine._WEIGHTS),  # noqa: SLF001
        "passed": raw["passed"],
        "failure_counts": failures,
        "indeterminate_rows": len(raw.get("indeterminate") or []),
        "children": len(raw.get("curve") or []),
        "calibration_proposal_present": raw.get("calibration_proposal") is not None,
        "by_family": raw.get("by_family"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--embed-url", default="http://localhost:8946/embed")
    parser.add_argument(
        "--candidate-375",
        action="store_true",
        help="grade with the T3 candidate unit-mass weights 0.375/0.375/0.05/0.05/0.15 (no-regression check)",
    )
    args = parser.parse_args(argv)
    if args.candidate_375:
        cousin_engine._WEIGHTS = {  # noqa: SLF001 -- scorer-side weight override for the T3 check
            "behavior": 0.375,
            "semantic": 0.375,
            "telemetry": 0.05,
            "context": 0.05,
            "attack": 0.15,
        }

    scratch = args.scratch
    if scratch.exists() and any(scratch.iterdir()):
        raise SystemExit(f"{scratch} is not empty; use a fresh output directory")
    scratch.mkdir(parents=True, exist_ok=True)

    records = [bench.parent_reference_record(p) for p in bench.CALIB_PARENTS_V1]
    with Store(scratch / "snapshot_state.db") as store:
        snapshot = Organ(
            store=store,
            db_path=scratch / "organ_snapshot",
            embed_url=args.embed_url,
            query_embed_url=None,
            embedding_version=EMBED_VERSION,
            embed_client=httpx.Client(timeout=600.0),
        )
        try:
            snapshot.upsert_many(records, batch_size=16)
            if snapshot.stats()["row_count"] != len(records):
                raise RuntimeError("calibration snapshot did not hold exactly the four parents")
            report = bench.run_bench(snapshot, scratch)
        finally:
            snapshot.close()

    summary = _summarise(report, scratch)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "t2_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
