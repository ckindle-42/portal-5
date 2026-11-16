#!/usr/bin/env python3
"""Read indexed observation grids for one Splunk index and write them under --out."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from portal.modules.security.core.hunt.baselines import BASELINES  # noqa: E402
from portal.modules.security.core.hunt.observations import (  # noqa: E402
    budgeted_search,
    load_observations,
    observe,
    reorder,
    write_receipts,
)
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402


def _score_text(score: float | None) -> str:
    if score is None:
        return "   none"
    return f"{score:7.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument(
        "--out", required=True, help="directory for observations.jsonl, grids/ and progress.json"
    )
    parser.add_argument("--baseline", default="current", choices=BASELINES)
    parser.add_argument(
        "--from-grids",
        default=None,
        help="reorder a saved observations.jsonl onto --baseline; does not recompute",
    )
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    args = parser.parse_args()
    started = time.time()
    if args.from_grids:
        saved_dir = Path(args.from_grids)
        saved = json.loads((saved_dir / "progress.json").read_text())
        run = reorder(
            load_observations(saved_dir),
            args.baseline,
            saved.get("coverage"),
            saved.get("request_kinds"),
        )
        meta = {
            "index": args.index,
            "start": saved.get("start"),
            "end": saved.get("end"),
            "from_grids": args.from_grids,
            "reordered": True,
        }
    else:
        end = time.time() if args.end is None else args.end
        window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
        run = observe(budgeted_search(window), args.index, args.start, end, baseline=args.baseline)
        meta = {"index": args.index, "start": args.start, "end": end, "from_grids": ""}
    meta["elapsed_s"] = round(time.time() - started, 1)
    out = Path(args.out)
    write_receipts(out, run, meta)
    print(
        f"{len(run.observations)} observations, baseline={run.baseline} "
        f"coverage_complete={run.coverage_complete} in {meta['elapsed_s']}s -> {out}"
    )
    for obs in run.observations[:20]:
        print(
            f"{_score_text(obs.score)} {obs.kind:7} {obs.host:18} {obs.evidence['signal']:8} "
            f"{obs.entity[:60]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
