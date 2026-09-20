#!/usr/bin/env python3
"""CLOSEOUT_V1 P5 - CIP-007-6 calibration against the PROVE_THEN_SCALE baseline.

Compares the pairings the store holds for CIP-007-6 now against the pairings
recorded when PROVE_THEN_SCALE closed, and sorts the difference into four
buckets. It reports; it does not act. An automatic reconciler here would be
the verdict engine growing back.

  preserved         - same (requirement, section, relation) in both
  changed_relation  - same pairing, different relation type. ALWAYS a review
                      item: a relation should not move silently.
  lost              - baseline held it, the store no longer does
  new               - the store holds it, the baseline did not

Exit codes: 0 always (a comparison is a recording, not a gate).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
from typing import Any


def _pairs_from_store(repo: Any, standard: str) -> dict[tuple[str, str], str]:
    rows = repo._conn.execute(
        """SELECT src_ref, dst_ref, relation_type
             FROM relationship_assertions
            WHERE src_ref LIKE ? AND derivation = 'machine_determined'""",
        (f"{standard}%",),
    ).fetchall()
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
    ap.add_argument("--baseline", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from portal.modules.compliance.core.repository import Repository

    repo = Repository()
    try:
        current = _pairs_from_store(repo, args.standard)
    finally:
        repo.close()
    baseline = _pairs_from_baseline(args.baseline)

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
        "baseline_path": str(args.baseline),
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
