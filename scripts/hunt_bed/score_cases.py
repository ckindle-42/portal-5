#!/usr/bin/env python3
"""Score investigation cases against the out-of-band Kyoushi key (scorer plane only).

For each case: which attack stages (key label sets, minus the generic phase words) have at
least one of their keyed lines in the case's evidence, plus how much of the evidence is keyed
at all. A case that "sees the whole picture" covers many stages across both days.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict

_GENERIC = {"foothold", "escalate"}


def _stage(labels: list[str]) -> str:
    return "+".join(sorted(set(labels) - _GENERIC)) or "+".join(labels)


def _digest(host: str, source: str, raw: str) -> str:
    return hashlib.sha256(f"{host}|{source}|{raw}".encode()).hexdigest()[:24]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", required=True)
    ap.add_argument("--keys", required=True)
    args = ap.parse_args()
    stage_of: dict[str, str] = {}
    stage_size: Counter[str] = Counter()
    with open(args.keys) as fh:
        for raw in fh:
            k = json.loads(raw)
            stage_of[k["digest"]] = _stage(k["labels"])
            stage_size[stage_of[k["digest"]]] += 1
    with open(args.cases) as fh:
        cases = json.load(fh)["cases"]
    print(f"key stages: {dict(stage_size)}")
    for i, case in enumerate(cases, 1):
        hit: dict[str, int] = defaultdict(int)
        keyed = 0
        for ev in case["evidence"]:
            for host in (ev["host"], ev["host"].replace("-", "_")):
                stage = stage_of.get(_digest(host, ev["source"], ev["raw"]))
                if stage:
                    hit[stage] += 1
                    keyed += 1
                    break
        print(
            f"case {i} seeds={case['merged_from']} events={case['events']} "
            f"hosts={len(case['hosts'])} span={case['span_hours']}h keyed_events={keyed}\n"
            f"   stages covered {len(hit)}/{len(stage_size)}: {dict(hit)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
