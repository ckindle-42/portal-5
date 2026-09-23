#!/usr/bin/env python3
"""The edges ONE family sweep affirmed, rebuilt from its stored runs.

A re-sweep never retracts an edge: ``record_determination`` either writes a
new pairing or corroborates an existing one, and a requirement re-read without
naming a section leaves that section's edge exactly where it was. So the
store-wide set of reading-derived edges is the accumulation of every campaign
— measured at LOAD_AND_CONVERSE: the family re-sweep affirmed 190 of the 366
adjudicated edges; the other 176 came from earlier readings. A change to what
the reader sees (CITE_AND_SCOPE_V1 P2's scope line) can only show in what the
NEW reading affirms, never in a store-wide count that still holds every edge
the old reading wrote.

This script reads ``reading_runs`` for the mapping readings asked at or after
``--since`` and reports:

* ``affirmed`` — every assertion the sweep determined or corroborated (the
  set to adjudicate for the sweep's precision);
* against a baseline adjudication: baseline edges whose requirement WAS re-read
  and that the new reading re-affirmed vs no longer affirmed, each broken down
  by its baseline verdict — the scope effect measured without a new judgement,
  since a no-longer-affirmed UNSUPPORTED edge is contamination the reader
  declined, and a no-longer-affirmed SUPPORTED edge is recall it lost;
* baseline edges whose requirement this sweep did not re-read (no evidence
  either way — reported, never counted as dropped).

Writes nothing to the store.

    uv run python scripts/compliance/sweep_edge_set.py --since 2026-09-23T14:00:00 \\
        --baseline reports/compliance/load_and_converse/p6/adjudication_v2.json \\
        --out reports/compliance/cite_and_scope/p3/sweep_edge_set.json
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from portal.modules.compliance.core.repository import Repository  # noqa: E402

_AFFIRMING = ("determined", "corroborated")


def affirmed_by_runs(repo: Any, since: str, until: str = "") -> dict[str, Any]:
    """``{"refs": set of refs read, "affirmed": {assertion_id: outcome}}`` for
    the mapping readings asked in ``[since, until)``."""
    rows = repo._conn.execute(
        """SELECT asked_at, subject_ref, closure_json FROM reading_runs
           WHERE question LIKE '[mapping]%' AND asked_at >= ?
             AND (? = '' OR asked_at < ?)
           ORDER BY asked_at""",
        (since, until, until),
    ).fetchall()
    refs: set[str] = set()
    affirmed: dict[str, dict[str, Any]] = {}
    for row in rows:
        refs.add(str(row["subject_ref"]))
        closure = json.loads(row["closure_json"] or "{}")
        for outcome in (closure.get("determinations") or {}).get("outcomes", []):
            if outcome.get("action") in _AFFIRMING and outcome.get("assertion_id"):
                affirmed[str(outcome["assertion_id"])] = outcome
    return {"n_runs": len(rows), "refs": refs, "affirmed": affirmed}


def _read_ref_of(requirement_id: str, refs: set[str]) -> bool:
    """A baseline edge's requirement was re-read when its ref, or a ref it sits
    under (a Part under a read requirement), was a mapping subject."""
    return any(requirement_id == ref or requirement_id.startswith(ref + " ") for ref in refs)


def compare(baseline_rows: list[dict[str, Any]], refs: set[str], affirmed: set[str]) -> dict:
    by_std: dict[str, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: collections.defaultdict(collections.Counter)
    )
    for row in baseline_rows:
        if row["assertion_id"] in affirmed:
            state = "reaffirmed"
        elif _read_ref_of(str(row["requirement_id"]), refs):
            state = "no_longer_affirmed"
        else:
            state = "requirement_not_reread"
        by_std[str(row["standard"])][state][str(row.get("verdict"))] += 1
    family: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for states in by_std.values():
        for state, verdicts in states.items():
            family[state].update(verdicts)
    return {
        "family": {s: dict(v) for s, v in family.items()},
        "per_standard": {
            std: {s: dict(v) for s, v in states.items()} for std, states in sorted(by_std.items())
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", required=True, help="ISO timestamp the sweep started at")
    ap.add_argument("--until", default="", help="ISO timestamp the sweep ended at (optional)")
    ap.add_argument("--baseline", type=pathlib.Path, help="baseline adjudication receipt")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    repo = Repository()
    try:
        got = affirmed_by_runs(repo, args.since, args.until)
    finally:
        repo.close()
    affirmed = got["affirmed"]
    receipt: dict[str, Any] = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "since": args.since,
        "until": args.until,
        "n_runs": got["n_runs"],
        "n_refs_read": len(got["refs"]),
        "n_affirmed": len(affirmed),
        "affirmed_by_action": dict(collections.Counter(o["action"] for o in affirmed.values())),
        "affirmed_assertion_ids": sorted(affirmed),
        "refs_read": sorted(got["refs"]),
    }
    if args.baseline:
        base = json.loads(args.baseline.read_text())
        receipt["baseline"] = str(args.baseline)
        receipt["baseline_vs_sweep"] = compare(base["rows"], got["refs"], set(affirmed))
        receipt["baseline_note"] = (
            "no_longer_affirmed = the requirement was re-read and the new reading did not "
            "name this edge. By baseline verdict: UNSUPPORTED there is contamination the "
            "reader declined; SUPPORTED there is recall the reader lost. "
            "requirement_not_reread is no evidence either way."
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
    print(
        f"runs={got['n_runs']} refs={len(got['refs'])} affirmed={len(affirmed)} "
        f"{receipt['affirmed_by_action']}"
    )
    if "baseline_vs_sweep" in receipt:
        for state, verdicts in receipt["baseline_vs_sweep"]["family"].items():
            print(f"  baseline {state:24s} {verdicts}")
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
