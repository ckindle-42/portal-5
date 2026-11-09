#!/usr/bin/env python3
"""Dig from the top leads of a hunt run, live, and write the assembled cases."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portal.modules.security.core.hunt.engine import Burst, Lead  # noqa: E402
from portal.modules.security.core.hunt.investigate import Investigator, merge_cases  # noqa: E402
from portal.modules.security.core.review.window import SplunkWindowSource  # noqa: E402


def _lead(d: dict) -> Lead:
    lead = Lead(
        d["hour"],
        d["host"],
        d["novelty"],
        d["hosts_novel_that_hour"],
        [tuple(t) for t in d["novel_templates"]],
        span=d.get("span", 3600),
    )
    lead.bursts = [Burst(**b) for b in d["bursts"]]
    lead.score = d["score"]
    return lead


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--leads", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.leads) as fh:
        run = json.load(fh)
    leads = [_lead(d) for d in run["leads"][: args.top]]
    search = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    inv = Investigator(search, run["index"], 0.0, time.time())
    t0 = time.time()
    cases = []
    for rank, lead in enumerate(leads, 1):
        case = inv.investigate(lead)
        cases.append(case)
        s = case.summary()
        print(
            f"lead #{rank} {lead.host}@{lead.as_dict()['hour_utc']}: {s['events']} events, "
            f"{len(s['hosts'])} hosts, {s['sources']} sources, span {s['span_hours']}h, "
            f"pivots {[p['token'][:30] for p in s['pivots']][:8]}",
            flush=True,
        )
    merged = merge_cases(cases)
    out = {
        "index": run["index"],
        "elapsed_s": round(time.time() - t0, 1),
        "cases": [{**c.summary(), "evidence": list(c.events.values())} for c in merged],
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh)
    print(f"{len(cases)} investigations -> {len(merged)} cases in {out['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
