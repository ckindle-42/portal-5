#!/usr/bin/env python3
"""CLOSEOUT_V1 P5 - CIP-007-6 calibration against the pre-sweep baseline.

Compares the pairings the store holds for CIP-007-6 now against the pairings
it held before the closeout re-sweep wrote anything, and sorts the difference
into four buckets. It reports; it does not act. An automatic reconciler here
would be the verdict engine growing back.

  preserved         - same (requirement, section, relation) in both
  changed_relation  - same pairing, different relation type. ALWAYS a review
                      item: a relation should not move silently.
  lost              - baseline held it, the store no longer does
  new               - the store holds it, the baseline did not

Basis (adaptation, recorded): the task pointed --baseline at the
PROVE_THEN_SCALE sweep artifact, but that artifact holds per-ref COUNTS only —
no pair exists in it, and none exists in the campaign report either, so a
pair-level calibration against it would have compared two empty sets and
printed a dishonest row of zeros. The pre-closeout STORE BACKUP (P0, taken
before the sweep wrote a determination) is the only true pair-level record of
the pre-sweep state, so ``--baseline-db`` reads pairings from it and this
receipt records which basis was used.

Reading-derived pairings are rows where the derivation names a reading
(``reading`` or ``...|reading`` from a corroboration) or the status is
``machine_determined`` — the task's ``derivation = 'machine_determined'``
matched nothing, because ``machine_determined`` is a STATUS in this schema and
corroboration APPENDS ``|reading`` to a compound derivation.

Exit codes: 0 always (a comparison is a recording, not a gate).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sqlite3
import sys
from typing import Any

# derivation names a reading: bare, or appended to an existing derivation by a
# corroboration. `semantic_reading` is a different writer and must not match.
_READING_HELD = (
    "status = 'machine_determined' OR derivation = 'reading' OR derivation LIKE '%|reading'"
)


def _pairs_from_store(repo: Any, standard: str) -> dict[tuple[str, str], str]:
    rows = repo._conn.execute(
        f"""SELECT src_ref, dst_ref, relation_type, status, derivation
              FROM relationship_assertions
             WHERE src_ref LIKE ? AND {_READING_HELD}""",
        (f"{standard}%",),
    ).fetchall()
    return {(str(r[0]), str(r[1])): str(r[2]) for r in rows}


def _pairs_from_db(path: pathlib.Path, standard: str) -> dict[tuple[str, str], str]:
    """The pairings a STORE SNAPSHOT held — the P0 pre-sweep backup."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"""SELECT src_ref, dst_ref, relation_type
                  FROM relationship_assertions
                 WHERE src_ref LIKE ? AND {_READING_HELD}""",
            (f"{standard}%",),
        ).fetchall()
    finally:
        conn.close()
    return {(str(r[0]), str(r[1])): str(r[2]) for r in rows}


def _pairs_from_baseline(path: pathlib.Path) -> dict[tuple[str, str], str]:
    """Baseline receipts carry determinations inside per-ref cells. Accept both
    the flat and the nested shape rather than assuming one."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out: dict[tuple[str, str], str] = {}

    def _absorb(entry: dict[str, Any]) -> None:
        req = str(entry.get("requirement_id") or entry.get("src_ref") or "")
        sec = str(entry.get("section_id") or entry.get("dst_ref") or "")
        rel = str(entry.get("relation_type") or "").upper()
        if req and sec and rel:
            out[(req, sec)] = rel

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            if {"requirement_id", "section_id"} <= node.keys() or {
                "src_ref",
                "dst_ref",
            } <= node.keys():
                _absorb(node)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--standard", default="CIP-007-6")
    ap.add_argument(
        "--baseline",
        type=pathlib.Path,
        default=None,
        help="a JSON receipt carrying pair-level determinations",
    )
    ap.add_argument(
        "--baseline-db",
        type=pathlib.Path,
        default=None,
        help="a STORE SNAPSHOT (the P0 pre-sweep backup) — the only "
        "pair-level record of the pre-sweep state",
    )
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()
    if bool(args.baseline) == bool(args.baseline_db):
        print("FAIL: exactly one of --baseline / --baseline-db", file=sys.stderr)
        return 3

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        current = _pairs_from_store(repo, args.standard)
    finally:
        repo.close()
    if args.baseline_db:
        baseline = _pairs_from_db(args.baseline_db, args.standard)
        basis = f"store snapshot {args.baseline_db} (reading-derived pairings)"
    else:
        baseline = _pairs_from_baseline(args.baseline)
        basis = f"json receipt {args.baseline}"

    preserved, changed, lost, new = [], [], [], []
    for key, rel in baseline.items():
        if key not in current:
            lost.append({"requirement": key[0], "section": key[1], "relation": rel})
        elif current[key] != rel:
            changed.append(
                {
                    "requirement": key[0],
                    "section": key[1],
                    "baseline_relation": rel,
                    "current_relation": current[key],
                }
            )
        else:
            preserved.append({"requirement": key[0], "section": key[1], "relation": rel})
    for key, rel in current.items():
        if key not in baseline:
            new.append({"requirement": key[0], "section": key[1], "relation": rel})

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "standard": args.standard,
        "baseline_path": str(args.baseline or args.baseline_db),
        "baseline_basis": basis,
        "baseline_pairs": len(baseline),
        "current_pairs": len(current),
        "summary": {
            "preserved": len(preserved),
            "changed_relation": len(changed),
            "lost": len(lost),
            "new": len(new),
        },
        "preserved": preserved,
        "changed_relation": changed,
        "lost": lost,
        "new": new,
        "interpretation": (
            "changed_relation is always a review item. lost is legitimate when the "
            "re-reading refused the citation under the same checker; it is a "
            "regression when the pairing simply vanished. new pairings passed the "
            "same checker as any other and get no special treatment. Nothing here "
            "is auto-actioned."
        ),
        "verdict": "RECORDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2))
    s = receipt["summary"]
    print(f"WROTE {args.out}")
    print(
        f"  preserved {s['preserved']}  changed {s['changed_relation']}  "
        f"lost {s['lost']}  new {s['new']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
