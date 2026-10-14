#!/usr/bin/env python3
"""Classify the model-fleet closeout register, and say what each removal costs.

WFE_ROOT_FIX program, Part 1 Phase 3 build step 8. The closeout
(`docs/MODEL_FLEET_CLOSEOUT_20260906.tasks.json`) is the authoritative
disposition register: every identity is INTEGRATED, RETAINED_FOR_PURPOSE or
REMOVED_CLOSED. What it does not say is whether a removal can be undone, and
which removals rest on a measurement the instrument audits found biased.

This derives both, mechanically, from the register itself:

  restorable    the identity was present at closeout and is an Ollama manifest,
                so `ollama pull <tag>` restores it and `model_layer_digests`
                verifies the restore is the same artifact;
  unrestorable  it was already absent at closeout, or it is an oMLX directory
                whose upstream source the register never recorded.

An unrestorable removal enters `tests/wfe/candidate_queue.yaml` with
`available: false`, so every cell it could have had is MISSING and the
disposition it supports can only ever be NO_DECISION.

Usage:
    uv run python scripts/wfe_disposition_backfill.py            # report
    uv run python scripts/wfe_disposition_backfill.py --write     # receipt + queue
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CLOSEOUT = REPO / "docs" / "MODEL_FLEET_CLOSEOUT_20260906.tasks.json"
RECEIPT = REPO / "docs" / "WFE_DISPOSITION_BACKFILL_20261014.json"
QUEUE = REPO / "tests" / "wfe" / "candidate_queue.yaml"

#: The removals the 2026-10-13 audits found resting on a biased measurement.
#: Four are judgment-probe-v6 stop-rule verdicts, one is the research probe.
#: Specified in docs/WFE_ROOT_CAUSES_20261013.md, "Decisions at risk".
AT_RISK = {
    "ollama:command-r:35b-08-2024-q4_K_M": "judgment probe v6: the stop rule's 'else REMOVED' fired",
    "ollama:granite4.1:8b-q8_0": "judgment probe v6: stop rule fired on +0.06 exact (about 2 of 30 tasks)",
    "ollama:granite4.2:30b-q4_K_M": "judgment probe v6: stop rule fired on a like-for-like comparator",
    "ollama:hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:Q4_K_M": "judgment probe v6: duplicate-quant stop rule fired on exact parity",
    "ollama:portal5/xyz-aquila-mini:q4_k_m-ctx16k": "research probe: the lane instrument's checkers were weak (defect 10)",
}

#: Every classification the backfill assigns.
CLASSES = ("integrated", "retained_for_purpose", "removed_restorable", "removed_unrestorable")


def classify(item: dict) -> tuple[str, str, str]:
    """(class, restorability, the exact recipe or the reason it cannot be restored)."""
    disposition = str(item.get("final_disposition") or "")
    present = item.get("observed_present") is True
    kind = str(item.get("kind") or "")
    identity = str(item.get("exact_identity") or item.get("item_id") or "")
    digests = [d for d in (item.get("model_layer_digests") or []) if d]
    if disposition == "INTEGRATED":
        return "integrated", "n/a", "in service; nothing to restore"
    if disposition == "RETAINED_FOR_PURPOSE":
        return "retained_for_purpose", "n/a", "kept for a named purpose; nothing to restore"
    if present and kind == "ollama_manifest":
        verify = f"; verify with model_layer_digests ({len(digests)} layer(s))" if digests else ""
        return (
            "removed_restorable",
            "restorable",
            f"ollama pull {identity}{verify}",
        )
    if not present:
        return (
            "removed_unrestorable",
            "unrestorable",
            "already absent from the store at closeout and the register records no upstream source",
        )
    return (
        "removed_unrestorable",
        "unrestorable",
        f"a {kind} directory: the register records no upstream source to re-obtain it from",
    )


def backfill() -> dict:
    register = json.loads(CLOSEOUT.read_text())
    items = register["items"]
    rows = []
    for item in items:
        cls, restorable, recipe = classify(item)
        rows.append(
            {
                "item_id": item["item_id"],
                "exact_identity": item.get("exact_identity"),
                "kind": item.get("kind"),
                "disposition": item.get("final_disposition"),
                "class": cls,
                "restorable": restorable,
                "recipe": recipe,
                "at_risk": AT_RISK.get(item["item_id"]),
                "logical_bytes": item.get("logical_bytes") or item.get("logical_referenced_bytes"),
            }
        )
    counts = collections.Counter(r["class"] for r in rows)
    return {
        "source": str(CLOSEOUT.relative_to(REPO)),
        "determination_ref": register.get("determination_ref"),
        "determination_date": register.get("determination_date"),
        "item_count": len(items),
        "classes": dict(sorted(counts.items())),
        "at_risk_first": [r for r in rows if r["at_risk"]],
        "unrestorable": [r for r in rows if r["restorable"] == "unrestorable"],
        "rows": rows,
    }


def queue_entries(rows: list[dict]) -> dict:
    """The unrestorable removals, as queue entries with `available: false`."""
    out: dict = {}
    for r in rows:
        if r["restorable"] != "unrestorable":
            continue
        identity = str(r["exact_identity"] or r["item_id"])
        entry = {
            "lineage": identity.split(":")[0],
            "available": False,
            "intended": [],
            "removed_at_closeout": True,
            "note": r["recipe"],
        }
        if r["at_risk"]:
            entry["at_risk"] = r["at_risk"]
        out[identity] = entry
    return out


def merge_queue(entries: dict) -> int:
    doc = yaml.safe_load(QUEUE.read_text()) or {}
    models = doc.setdefault("models", {})
    added = 0
    for identity, entry in entries.items():
        if identity not in models:
            models[identity] = entry
            added += 1
        else:
            models[identity].update(entry)
    QUEUE.write_text(yaml.safe_dump(doc, sort_keys=True, width=100))
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write the receipt and the queue")
    args = ap.parse_args()
    report = backfill()
    print(f"classified {report['item_count']} item(s): {report['classes']}")
    print(f"\nmeasurement-based removals ({len(report['at_risk_first'])}):")
    for r in report["at_risk_first"]:
        print(f"  {r['item_id']}\n      {r['at_risk']}\n      {r['restorable']}: {r['recipe']}")
    un = report["unrestorable"]
    print(f"\nunrestorable removals: {len(un)}")
    if args.write:
        RECEIPT.write_text(json.dumps(report, indent=1) + "\n")
        added = merge_queue(queue_entries(un))
        print(f"wrote {RECEIPT.relative_to(REPO)}; queue +{added} unavailable entry(ies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
