#!/usr/bin/env python3
"""Out-of-band, entity-level answer key for Splunk BOTS v1/v2/v3 (scorer plane only).

Official BOTS answers are released by Splunk on request only (bots@splunk.com). This key is
transcribed from public write-ups, each value cited, and is admitted only when a live audit
finds it in the dataset's index. Values are split by role:

  artefact -- specific to the attack (file names, attacker domains/IPs, hashes, created accounts)
  asset    -- the victim host/user/server; also carries ordinary traffic, so it can never be
              the only thing a case matched

A case "finds" a scenario when it contains at least one of the scenario's artefacts; asset
matches are reported but never count on their own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The cited answer values live out of band (they include values such as a leaked AWS access
# key from the BOTS v3 data, which must never be committed): one JSON list of
# {"dataset", "scenario", "value", "role", "citations"} passed with --source.


def audit(search, index: str, value: str) -> dict:
    q = f'| tstats count dc(sourcetype) as st dc(host) as hosts where index={index} TERM("{value}")'
    rows = list(search.iter_post(q, 0, 2e9))
    row = dict(rows[0]) if rows else {}
    if row.get("count", "0") == "0":
        q = f'search index={index} "{value}" | head 1000 | stats count dc(sourcetype) as st dc(host) as hosts'
        rows = list(search.iter_post(q, 0, 2e9))
        row = dict(rows[0]) if rows else {}
    return {
        "count": int(row.get("count", 0) or 0),
        "sourcetypes": int(row.get("st", 0) or 0),
        "hosts": int(row.get("hosts", 0) or 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, type=Path, help="cited key values (out of band)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    key = json.loads(args.source.read_text())
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import os

    from portal.modules.security.core.review.window import SplunkWindowSource

    search = SplunkWindowSource(url=os.environ.get("LAB_SPLUNK_URL"), timeout_seconds=600)
    admitted = 0
    with open(args.out, "w") as fh:
        for row in key:
            dataset, scenario, value = row["dataset"], row["scenario"], row["value"]
            role, cites = row["role"], row["citations"]
            a = audit(search, dataset, value)
            ok = a["count"] > 0
            admitted += ok
            fh.write(
                json.dumps(
                    {
                        "dataset": dataset,
                        "scenario": scenario,
                        "value": value,
                        "role": role,
                        "citations": cites,
                        "audit": a,
                        "admitted": ok,
                    }
                )
                + "\n"
            )
            print(f"{'OK ' if ok else 'NO '} {dataset} {scenario:22} {role:8} {value[:50]:50} {a}")
    print(f"admitted {admitted}/{len(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
