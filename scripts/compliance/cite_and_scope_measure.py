#!/usr/bin/env python3
"""CITE_AND_SCOPE_V1 §P3 — assemble ``p3/measured.json`` from the receipts.

Nothing here is measured afresh: it folds the sweep-set adjudication, the
sweep edge set, and the conversational and product receipts into the one
shape the §P3 comparison reads, with edges beside precision everywhere.

Two family numbers, because the store only ever accumulates edges (see
``sweep_edge_set.py``):

* ``family_*`` / ``per_standard`` — the P3 sweep's OWN affirmed edges,
  adjudicated. Compare against ``baseline_sweep_set``: the same measure over
  the previous sweep's affirmed edges, from the baseline adjudication. That is
  the like-for-like comparison.
* ``baseline_store_wide`` — p0's 366-edge figure, kept for continuity. It
  mixes every campaign's readings and is NOT the comparator for the scope fix.

    uv run python scripts/compliance/cite_and_scope_measure.py \\
        --baseline reports/compliance/cite_and_scope/p0/baseline.json \\
        --baseline-adjudication reports/compliance/load_and_converse/p6/adjudication_v2.json \\
        --baseline-edge-set reports/compliance/cite_and_scope/p3/baseline_edge_set.json \\
        --adjudication reports/compliance/cite_and_scope/p3/adjudication_p3.json \\
        --edge-set reports/compliance/cite_and_scope/p3/sweep_edge_set.json \\
        --conversational reports/compliance/cite_and_scope/p3/conversational/conversational_proof.json \\
        --product reports/compliance/cite_and_scope/p3/product/product_questions_family.json \\
        --out reports/compliance/cite_and_scope/p3/measured.json
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import pathlib
import sys
from typing import Any


def _load(path: pathlib.Path | None) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path else None


def _per_standard(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        tally[str(row["standard"])][str(row.get("verdict"))] += 1
    return {
        std: {
            "n": sum(c.values()),
            "precision": round(c["SUPPORTED"] / sum(c.values()), 4) if c else None,
            **{k.lower(): v for k, v in c.items()},
        }
        for std, c in sorted(tally.items())
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    supported = sum(1 for r in rows if r.get("verdict") == "SUPPORTED")
    return {
        "edges": n,
        "precision": round(supported / n, 4) if n else None,
        "per_standard": _per_standard(rows),
    }


def _question_set(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if receipt is None:
        return {"passed": None, "total": None, "failures_by_check": {}}
    failures: collections.Counter = collections.Counter()
    for row in receipt.get("rows", []):
        if row.get("verdict") == "FAIL":
            failures.update(k for k, v in (row.get("checks") or {}).items() if v is False)
    return {
        "passed": receipt.get("n_passed"),
        "total": receipt.get("n_questions"),
        "failures_by_check": dict(failures),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=pathlib.Path, required=True)
    ap.add_argument("--baseline-adjudication", type=pathlib.Path, required=True)
    ap.add_argument("--baseline-edge-set", type=pathlib.Path, required=True)
    ap.add_argument("--adjudication", type=pathlib.Path, required=True)
    ap.add_argument("--edge-set", type=pathlib.Path, required=True)
    ap.add_argument("--conversational", type=pathlib.Path)
    ap.add_argument("--product", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    baseline = _load(args.baseline) or {}
    base_adj = _load(args.baseline_adjudication) or {}
    base_set = set((_load(args.baseline_edge_set) or {}).get("affirmed_assertion_ids", []))
    adj = _load(args.adjudication) or {}
    edge_set = _load(args.edge_set) or {}
    if adj.get("n_missing_verdict"):
        print(f"FAIL: {adj['n_missing_verdict']} edges have no verdict", file=sys.stderr)
        return 3

    now = _summary(adj.get("rows", []))
    prior = _summary([r for r in base_adj.get("rows", []) if r["assertion_id"] in base_set])
    conversational = _question_set(_load(args.conversational))
    product = _question_set(_load(args.product))
    measured = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "family_edges": now["edges"],
        "family_precision": now["precision"],
        "per_standard": now["per_standard"],
        "n_carried_verdicts": adj.get("n_carried"),
        "baseline_sweep_set": {
            "family_edges": prior["edges"],
            "family_precision": prior["precision"],
            "per_standard": prior["per_standard"],
        },
        "baseline_store_wide": {
            "family_edges": baseline.get("family_edges"),
            "family_precision": baseline.get("family_precision"),
        },
        "scope_effect_without_judgement": edge_set.get("baseline_vs_sweep"),
        "conversational_passed": conversational["passed"],
        "conversational_total": conversational["total"],
        "conversational_failures_by_check": conversational["failures_by_check"],
        "product_passed": product["passed"],
        "product_total": product["total"],
        "product_failures_by_check": product["failures_by_check"],
        "attribution_note": (
            "The family sweep reads reading_material.render with handles, so the quote "
            "contract does not reach it: the sweep-set precision move is the scope line's. "
            "The conversational and product sets read the same material through "
            "compliance_context and see BOTH changes; their move is not attributable to "
            "either fix alone."
        ),
        "inputs": {k: str(v) for k, v in vars(args).items() if v is not None},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(measured, indent=2, default=str) + "\n")
    print(
        f"sweep set  {prior['edges']} @ {prior['precision']}  ->  "
        f"{now['edges']} @ {now['precision']}"
    )
    for std in sorted(set(prior["per_standard"]) | set(now["per_standard"])):
        b, m = prior["per_standard"].get(std, {}), now["per_standard"].get(std, {})
        print(
            f"  {std:16s} n {b.get('n')}->{m.get('n')}  "
            f"prec {b.get('precision')} -> {m.get('precision')}"
        )
    print(f"conversational {conversational['passed']}/{conversational['total']}")
    print(f"product        {product['passed']}/{product['total']}")
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
