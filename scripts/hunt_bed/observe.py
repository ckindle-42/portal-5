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

from portal.modules.security.core.hunt.observations import (  # noqa: E402
    budgeted_search,
    observe,
)
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument(
        "--out", required=True, help="directory for observations.jsonl and progress.json"
    )
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    args = parser.parse_args()
    end = time.time() if args.end is None else args.end
    window = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    started = time.time()
    run = observe(budgeted_search(window), args.index, args.start, end)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(obs.as_dict(), sort_keys=True) for obs in run.observations]
    (out / "observations.jsonl").write_text(("\n".join(lines) + "\n") if lines else "")
    progress = {
        "index": args.index,
        "start": args.start,
        "end": end,
        "elapsed_s": round(time.time() - started, 1),
        "observation_count": len(run.observations),
        "order": "(-score, kind, host, entity, signal, hour)",
        "coverage_complete": run.coverage_complete,
        "coverage": run.coverage,
        "request_kinds": run.request_kinds,
    }
    (out / "progress.json").write_text(json.dumps(progress, indent=1, sort_keys=True) + "\n")
    print(
        f"{len(run.observations)} observations, coverage_complete={run.coverage_complete} "
        f"in {progress['elapsed_s']}s -> {out}"
    )
    for obs in run.observations[:20]:
        print(
            f"{obs.score:7.2f} {obs.kind:7} {obs.host:18} {obs.evidence['signal']:8} "
            f"{obs.entity[:60]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
