#!/usr/bin/env python3
"""Score a hunt run on a BOTS index against the cited, audited entity key (scorer plane only).

Truth per scenario = where its *artefacts* (attack-specific values) occur: host x minute,
looked up in Splunk by the scorer after the hunt. A lead hits a scenario when its host and
[start, start+span) contain one of those artefact minutes. A case finds a scenario when its
evidence text contains one of the scenario's artefacts. Assets (victim hosts/users) are listed
but never count on their own.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def artefact_minutes(search, index: str, key: list[dict]) -> dict[str, dict[str, list[int]]]:
    out: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for k in key:
        if k["dataset"] != index or k["role"] != "artefact" or not k.get("admitted"):
            continue
        q = f'| tstats count where index={index} TERM("{k["value"]}") by host _time span=1m'
        rows = list(search.iter_post(q, 0, 2e9))
        if not rows:
            q = f'search index={index} "{k["value"]}" | bin _time span=1m | stats count by host _time'
            rows = list(search.iter_post(q, 0, 2e9))
        for r in rows:
            out[k["scenario"]][r["host"].lower()].append(int(float(r["_time"])))
    for hosts in out.values():
        for ts in hosts.values():
            ts.sort()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", required=True)
    ap.add_argument("--key", required=True, type=Path)
    ap.add_argument("--leads", required=True)
    ap.add_argument("--cases", help="hunt job / cases JSON with an `evidence` list per case")
    args = ap.parse_args()
    from portal.modules.security.core.review.window import SplunkWindowSource

    key = [json.loads(line) for line in args.key.read_text().splitlines()]
    search = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    truth = artefact_minutes(search, args.index, key)
    with open(args.leads) as fh:
        leads = json.load(fh)["leads"]

    def hits(lead: dict) -> set[str]:
        lo, hi = lead["hour"], lead["hour"] + lead.get("span", 3600)
        found = set()
        for sc, hosts in truth.items():
            ts = hosts.get(lead["host"].lower(), [])
            i = bisect.bisect_left(ts, lo)
            if i < len(ts) and ts[i] < hi:
                found.add(sc)
        return found

    hs = [hits(lead) for lead in leads]
    print(f"{args.index}: scenarios with located artefacts {len(truth)}: {sorted(truth)}")
    first: dict[str, int] = {}
    for rank, h in enumerate(hs, 1):
        for sc in h:
            first.setdefault(sc, rank)
    for n in (10, 25, 50, 100):
        found = {sc for h in hs[:n] for sc in h}
        print(
            f"top {n:3}: scenarios {len(found)}/{len(truth)}  false leads "
            f"{sum(1 for h in hs[:n] if not h)}/{n}"
        )
    print("first-hit rank per scenario:", dict(sorted(first.items(), key=lambda kv: kv[1])))
    if args.cases:
        with open(args.cases) as fh:
            cases = json.load(fh)["cases"]
        arts = [k for k in key if k["dataset"] == args.index and k["role"] == "artefact"]
        for i, c in enumerate(cases, 1):
            text = "\n".join(e["raw"] for e in c["evidence"]).lower()
            got = sorted({(k["scenario"], k["value"]) for k in arts if k["value"].lower() in text})
            core_text = "\n".join(e["raw"] for e in c.get("core", [])).lower()
            core_got = sorted(
                {(k["scenario"], k["value"]) for k in arts if k["value"].lower() in core_text}
            )
            print(f"case {i}: events {c['events']} artefacts {got}")
            print(
                f"case {i}: core {c.get('core_events', '-')} core_hosts {c.get('core_hosts', '-')} core artefacts {core_got}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
