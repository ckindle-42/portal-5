#!/usr/bin/env python3
"""Run the blind hunt engine live against one Splunk index and write the ranked leads."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.hunt.engine import hunt  # noqa: E402
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", required=True)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=time.time())
    ap.add_argument("--candidates", type=int, default=40)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    t0 = time.time()
    leads = hunt(
        SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600),
        args.index,
        args.start,
        args.end,
        candidates=args.candidates,
    )
    payload = {
        "index": args.index,
        "elapsed_s": round(time.time() - t0, 1),
        "leads": [lead.as_dict() for lead in leads],
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=1)
    print(f"{len(leads)} leads in {payload['elapsed_s']}s -> {args.out}")
    for lead in leads[:15]:
        top = lead.bursts[0] if lead.bursts else None
        print(
            f"{lead.score:7.2f} {lead.as_dict()['hour_utc']} {lead.host:18} "
            f"novelty={lead.novelty} "
            + (
                f"burst={top.token[:40]} {top.this_hour}/{top.prior_median} z={top.z} "
                f"links={len(top.links)}"
                if top
                else ""
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
