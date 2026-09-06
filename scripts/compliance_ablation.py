#!/usr/bin/env python3
"""Ablation study (TASK_COMPLIANCE_REASONING_V6 P8, Y22).

Runs the 30-case judgment probe through the real gate + council pipeline with
one component disabled at a time, and reports the F2 delta per arm — mirroring
GraphCompliance's ablation.

Arms:
  full                    — the shipped pipeline
  no_typing               — every node treated as an actor-CU (premise/meta
                            gating off)
  no_organization_graph   — the structured candidate filter off; the candidate
                            is always passed straight to the council
  no_vocabulary_bridge    — actor alignment always returns True
  no_reference_traversal  — the reference/exception closure is emptied
  single_seat             — one council seat instead of the full roster

Model calls hit Ollama; run this AFTER the judgment sweep, not concurrently
(sequential bench only). ``--seats`` overrides the roster;
``--limit N`` runs the first N cases for a smoke check.

    uv run python scripts/compliance_ablation.py --seats granite4.2:30b-q4_K_M \
        hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k \
        hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL-ctx64k
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "tests" / "compliance_probe" / "judgment_probe_v6.jsonl"
RESULTS = REPO / "tests" / "benchmarks" / "results"

_VIOLATION = {"PARTIAL", "CONTRADICTED", "ABSENT"}
ARMS = (
    "full",
    "no_typing",
    "no_organization_graph",
    "no_vocabulary_bridge",
    "no_reference_traversal",
    "single_seat",
)


def _f2(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 0.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return 5 * p * r / (4 * p + r) if (p + r) else 0.0


def _cases(limit: int | None) -> list[dict]:
    rows = [json.loads(x) for x in PROBE.read_text().splitlines() if x.strip()]
    return rows[:limit] if limit else rows


def _run_arm(arm: str, cases: list[dict], seats: list[dict[str, str]]) -> dict:
    from portal.modules.compliance.core import gate as gate_mod
    from portal.modules.compliance.core import vocabulary_bridge as vb
    from portal.modules.compliance.core.applicability import AssetScope
    from portal.modules.compliance.core.operations import judge
    from portal.modules.compliance.core.policy_graph import build_policy_graph

    g = build_policy_graph()
    if arm == "no_typing":
        for n in g.nodes:
            n.node_type = "actor_cu"
    if arm == "no_reference_traversal":
        g.edges = [e for e in g.edges if e.get("rel") != "REFERS_TO"]

    orig_align = vb.align_actor
    if arm == "no_vocabulary_bridge":
        vb.align_actor = lambda ia, ga, v: vb.ActorAlignment(
            True, 1.0, ga, ia, [], "bridge ablated"
        )
        gate_mod.align_actor = vb.align_actor

    arm_seats = seats[:1] if arm == "single_seat" else seats
    scope = AssetScope(
        impact_present={"high", "medium", "low"},
        associated_present={"eacms", "pacs", "pca"},
        has_erc=True,
        has_control_center=True,
        declared_by="operator:ablation",
    )
    tp = fp = fn = tn = 0
    per_case = []
    for c in cases:
        ref = c["governing_ref"]
        com = (
            []
            if c["candidate_text"] is None
            else [
                {
                    "commitment_id": f"probe:{c['id']}",
                    "document_id": "probe",
                    "standard_folder": "" if arm == "no_organization_graph" else ref.split(" ")[0],
                    "actor": "OT Security Team",
                    "text": c["candidate_text"],
                }
            ]
        )
        try:
            d = judge(ref, scope=scope, org_commitments=com, seats=arm_seats, policy_graph=g)
            pred = d.determination
        except Exception as e:  # noqa: BLE001
            pred = f"ERR:{e}"
        gold_pos = c["gold_label"] in _VIOLATION
        pred_pos = pred in _VIOLATION
        if gold_pos and pred_pos:
            tp += 1
        elif gold_pos:
            fn += 1
        elif pred_pos:
            fp += 1
        else:
            tn += 1
        per_case.append({"id": c["id"], "gold": c["gold_label"], "pred": pred})

    vb.align_actor = orig_align
    gate_mod.align_actor = orig_align
    return {
        "arm": arm,
        "F2": round(_f2(tp, fp, fn), 4),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "per_case": per_case,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seats", nargs="+", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    seats = [{"id": m.split("/")[-1][:12], "label": m, "model": m} for m in args.seats]
    cases = _cases(args.limit)
    results = {}
    full_f2 = None
    for arm in ARMS:
        print(f"=== {arm} ===")
        r = _run_arm(arm, cases, seats)
        results[arm] = r
        if arm == "full":
            full_f2 = r["F2"]
        delta = "" if full_f2 is None or arm == "full" else f"  (Δ {r['F2'] - full_f2:+.4f})"
        print(f"  F2 {r['F2']}{delta}  confusion {r['confusion']}")
    out = args.out or RESULTS / "compliance_ablation.json"
    out.write_text(
        json.dumps({"n_cases": len(cases), "seats": args.seats, "arms": results}, indent=2)
    )
    print(f"\nwrote {out}")
    print(f"\n{'arm':26} {'F2':>8} {'delta vs full':>14}")
    for arm, r in results.items():
        d = "-" if arm == "full" else f"{r['F2'] - results['full']['F2']:+.4f}"
        print(f"{arm:26} {r['F2']:8.4f} {d:>14}")


if __name__ == "__main__":
    main()
