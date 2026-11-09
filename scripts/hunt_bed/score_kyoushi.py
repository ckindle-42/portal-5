#!/usr/bin/env python3
"""Score a hunt run against the out-of-band Kyoushi key (scorer plane; the engine never sees it).

Truth unit: host-hour holding keyed lines, grouped into attack phases by day. Reports, per
phase, the best rank of any of its host-hours among the leads, recall@N for N in (10, 25, 50),
and how many of the top-N leads sit on host-hours with no keyed line (false leads).
Host spellings differ by source in real Splunk (`intranet_server` vs `intranet-server`); the
scorer treats '-' and '_' as the same host -- that normalisation lives here, never in the engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_native import parse_time  # noqa: E402


def _h(host: str) -> str:
    return host.replace("-", "_")


def keyed_host_hours(gather: str, keys_path: str, year: int) -> dict[tuple[int, str], int]:
    by_file: dict[tuple[str, str], list[int]] = defaultdict(list)
    with open(keys_path) as fh:
        for raw in fh:
            k = json.loads(raw)
            by_file[(k["host"], k["source"])].append(k["line"])
    out: dict[tuple[int, str], int] = defaultdict(int)
    for (host, source), lines in by_file.items():
        with open(f"{gather}/{host}/logs{source}", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        rows = text.split("\n")
        for ln in lines:
            t = parse_time(rows[ln - 1], year)
            if t is not None:
                out[(int(t) // 3600 * 3600, _h(host))] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--leads", required=True)
    ap.add_argument("--gather", required=True)
    ap.add_argument("--keys", required=True)
    ap.add_argument("--year", type=int, required=True)
    args = ap.parse_args()
    truth = keyed_host_hours(args.gather, args.keys, args.year)
    with open(args.leads) as fh:
        leads = json.load(fh)["leads"]
    ranked = [(lead["hour"], _h(lead["host"])) for lead in leads]
    phases: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for hh in truth:
        phases[time.strftime("%Y-%m-%d", time.gmtime(hh[0]))].append(hh)
    print(f"leads {len(ranked)}; keyed host-hours {len(truth)}")
    for day, hhs in sorted(phases.items()):
        ranks = sorted(ranked.index(hh) + 1 for hh in hhs if hh in ranked)
        print(
            f"phase {day}: {len(hhs)} keyed host-hours "
            f"({sum(truth[h] for h in hhs)} lines); ranks {ranks[:8]}; "
            f"missing {sum(1 for hh in hhs if hh not in ranked)}"
        )
    for n in (10, 25, 50):
        top = ranked[:n]
        hit_phases = {d for d, hhs in phases.items() if any(hh in top for hh in hhs)}
        false = sum(1 for hh in top if hh not in truth)
        print(f"top {n}: phases found {len(hit_phases)}/{len(phases)}  false leads {false}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
