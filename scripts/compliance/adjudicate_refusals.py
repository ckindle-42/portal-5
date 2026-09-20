#!/usr/bin/env python3
"""CLOSEOUT_V1 P6 - sort every sweep refusal into the three A6.3 categories.

  model_side_error  - the model paired across the jurisdiction line: named a
                      regulatory section where an operator section belongs, or
                      the reverse. A reading defect. (CIP-003-8: 18/20.)
  checker_strictness - the quoted sentence is semantically in the section but
                      not verbatim. A checker-relaxation CANDIDATE, recorded
                      and not admitted; relaxing the checker is its own task
                      with its own evidence.
  quote_discipline  - the quoted sentence is not in the section at all. A bad
                      reading.
  unclassified      - a refusal whose reason matches no rule. Counted and
                      listed in full, never silently folded into a bucket.

Admission is untouched: determinations that pass the checker were admitted by
`record_determination` during the sweep. This only classifies what it refused.

Exit codes: 0 always.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys
from typing import Any

FUZZY_FLOOR = 0.85

_REGULATORY_ID = re.compile(r"\bcsection-[0-9a-f]+\b", re.I)
_OPERATOR_ID = re.compile(r"\bisection-[0-9a-f]+\b", re.I)


def _fuzzy(a: str, b: str) -> float:
    """token_set_ratio in 0..1. rapidfuzz when present, difflib otherwise -
    the fallback is stated in the receipt so a number is never anonymous."""
    try:
        from rapidfuzz.fuzz import token_set_ratio

        return float(token_set_ratio(a, b)) / 100.0
    except ImportError:
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _fuzzy_backend() -> str:
    try:
        import rapidfuzz  # noqa: F401

        return "rapidfuzz.token_set_ratio"
    except ImportError:
        return "difflib.SequenceMatcher (rapidfuzz absent)"


def _section_text(repo: Any, section_id: str) -> str:
    try:
        row = repo._conn.execute(
            "SELECT text FROM source_sections WHERE section_id = ?", (section_id,)
        ).fetchone()
    except Exception:  # noqa: BLE001 - an unreadable section yields no text, never a guess
        return ""
    return str(row[0]) if row and row[0] else ""


def _classify(repo: Any, outcome: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    reason = str(outcome.get("reason", ""))
    section_id = str(outcome.get("section_id", ""))
    sentence = str(outcome.get("sentence", ""))
    detail: dict[str, Any] = {}

    # 1. jurisdiction crossing - decided on the id's own prefix, not on prose
    if section_id.startswith("csection-"):
        return ("model_side_error", "paired a regulatory section as the operator side", detail)
    if _REGULATORY_ID.search(reason) and "operator" in reason.lower():
        return ("model_side_error", reason, detail)

    # 2/3. quote present-but-paraphrased vs absent
    if sentence and section_id:
        body = _section_text(repo, section_id)
        if body:
            verbatim = sentence.strip() and sentence.strip() in body
            score = _fuzzy(sentence, body)
            detail = {"fuzzy_score": round(score, 4), "verbatim": bool(verbatim)}
            if not verbatim and score >= FUZZY_FLOOR:
                return (
                    "checker_strictness",
                    f"paraphrased but semantically present (score {score:.2f})",
                    detail,
                )
            if not verbatim:
                return (
                    "quote_discipline",
                    f"quoted sentence not found in the section (score {score:.2f})",
                    detail,
                )

    # an id the store cannot resolve is a reading defect, not a checker one
    if "not found" in reason.lower() or "does not resolve" in reason.lower():
        return ("model_side_error", reason, detail)

    return ("unclassified", reason or "no reason recorded", detail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from portal.modules.compliance.core.repository import Repository

    sweep_data = json.loads(args.sweep.read_text())

    refusals: list[dict[str, Any]] = []

    def _walk(node: Any, standard: str = "", ref: str = "") -> None:
        if isinstance(node, dict):
            standard = str(node.get("standard") or standard)
            ref = str(node.get("ref") or ref)
            outcomes = (node.get("determinations") or {}).get("outcomes")
            if isinstance(outcomes, list):
                for o in outcomes:
                    if isinstance(o, dict) and o.get("action") == "rejected":
                        refusals.append({**o, "standard": standard, "ref": ref})
            for v in node.values():
                _walk(v, standard, ref)
        elif isinstance(node, list):
            for v in node:
                _walk(v, standard, ref)

    _walk(sweep_data)

    repo = Repository()
    try:
        buckets: dict[str, list[dict[str, Any]]] = {
            "model_side_error": [],
            "checker_strictness": [],
            "quote_discipline": [],
            "unclassified": [],
        }
        for r in refusals:
            cat, why, detail = _classify(repo, r)
            buckets[cat].append(
                {
                    "standard": r.get("standard"),
                    "requirement": r.get("ref"),
                    "section_id": r.get("section_id"),
                    "relation_type": r.get("relation_type"),
                    "original_reason": r.get("reason"),
                    "classification_reason": why,
                    **detail,
                }
            )
    finally:
        repo.close()

    receipt = {
        "run_id": _dt.datetime.now(_dt.UTC).isoformat(),
        "sweep_receipt": str(args.sweep),
        "fuzzy_backend": _fuzzy_backend(),
        "fuzzy_floor": FUZZY_FLOOR,
        "n_refusals": len(refusals),
        "totals": {k: len(v) for k, v in buckets.items()},
        "categories": buckets,
        "admission_note": (
            "Nothing here is admitted. Determinations that passed the checker were "
            "admitted during the sweep by record_determination. checker_strictness "
            "is a candidate set for a future checker-relaxation task, not a backlog "
            "of edges waiting to be let in."
        ),
        "verdict": "RECORDED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"WROTE {args.out}")
    for k, v in receipt["totals"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
