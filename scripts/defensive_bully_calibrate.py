#!/usr/bin/env python3
"""Run the P6.8 cousin-calibration bench on an isolated Organ snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from portal.modules.security.core.bully import config as bully_config  # noqa: E402
from portal.modules.security.core.bully.cousin_calibration_bench import (  # noqa: E402
    corpus_parent_reference_record,
    load_specimen_corpus,
    run_baseline_bench,
)
from portal.modules.security.core.bully.organ import Organ  # noqa: E402
from portal.modules.security.core.bully.specimen_ledger import SpecimenLedger  # noqa: E402
from portal.modules.security.core.bully.store import Store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--ledger-root", type=Path)
    args = parser.parse_args(argv)
    run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or (bully_config.hunt_dir() / "artifacts" / "calibration" / run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = args.corpus or (
        bully_config.hunt_dir() / "artifacts" / "specimen_corpus_v2" / "specimen_corpus_v2.json"
    )
    ledger = SpecimenLedger(args.ledger_root or bully_config.hunt_dir() / "specimens")
    corpus = load_specimen_corpus(corpus_path)

    with Store(output_dir / "snapshot_state.db") as store:
        snapshot = Organ(store=store, db_path=output_dir / "organ_snapshot")
        try:
            for parent in corpus["specimens"]:
                if parent["source_lane"] == "attack_data":
                    snapshot.upsert(corpus_parent_reference_record(parent))
            seeded_rows = snapshot.stats()["row_count"]
            report = run_baseline_bench(
                snapshot,
                corpus_path=corpus_path,
                ledger=ledger,
                output_dir=output_dir,
            )
            final_rows = snapshot.stats()["row_count"]
        finally:
            snapshot.close()

    result = {
        "passed": report.passed,
        "output_dir": str(output_dir),
        "seeded_parent_rows": seeded_rows,
        "final_snapshot_rows": final_rows,
        "children_indexed": final_rows - seeded_rows,
        "calibration_proposal": report.calibration_proposal,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
