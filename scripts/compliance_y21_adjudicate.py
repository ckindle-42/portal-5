#!/usr/bin/env python3
"""Y21 — adjudicated error ceilings (TASK_COMPLIANCE_REASONING_V6 / V8).

Reads the seat-sweep debug JSONL (every case x seat carries the request, the
verbatim raw response, the parse, the per-field score, the gold and the packet
allowlist), stratifies a sample across seat x error-kind x category, and assigns
each disagreement one of four causes. No model calls — this is adjudication of
evidence already on disk.

The taxonomy is mechanical, derived from the recorded fields rather than from
reading prose, so two runs of this script agree:

  extraction  the model's output could not be read as the contract
              (schema_ok false, or the parse is empty/malformed)
  bridge      the determination is right but the CITATION is wrong — the
              vocabulary/reference mapping failed, not the reasoning
  gate        the answer flags something the packet allowlist forbids
              (must_not_flag_fp), i.e. the no-model gate should have caught it
  judgment    schema fine, citation fine, and the label is still wrong — a
              genuine reasoning error, the only class a better model fixes

Ceilings (V6 Y21): false-gap <= 10%, and zero UNRESOLVED false-supported.

    uv run python scripts/compliance_y21_adjudicate.py [--sample 40] [--out X.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEBUG_DIR = REPO / "coding_task/v9_compliance/private/runs/D0_20260906T185401Z/seat_sweep_debug"
# The three seats config/compliance/council.yaml actually runs. The sweep covers
# 13 candidates; ceilings are a property of the SHIPPED council, so the roster is
# reported separately from the full field.
ROSTER = {
    "granite4.1:30b-ctx16k",
    "mistral-small3.2:24b-instruct-2506-q4_K_M",
    "hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M-ctx32k",
}


def _load(debug_dir: Path) -> list[dict[str, Any]]:
    """One record per (seat, case). The seat is only on each file's preflight
    row, so it is attributed per file and stamped onto every case in it."""
    out: list[dict[str, Any]] = []
    for f in sorted(glob.glob(f"{debug_dir}/*.debug.jsonl")):
        seat, cases = None, []
        for line in Path(f).read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("_meta") == "preflight":
                seat = d.get("model")
            else:
                cases.append(d)
        for c in cases:
            c["seat"] = seat or Path(f).stem
            out.append(c)
    return out


def classify(row: dict[str, Any]) -> str | None:
    """None when the row is not a disagreement; else one of the four causes."""
    s = row.get("score") or {}
    clean = (
        s.get("correct")
        and s.get("citation_ok")
        and s.get("schema_ok")
        and not s.get("must_not_flag_fp")
    )
    if clean:
        return None
    if not s.get("schema_ok") or not row.get("parsed"):
        return "extraction"
    if s.get("must_not_flag_fp"):
        return "gate"
    if s.get("correct") and not s.get("citation_ok"):
        return "bridge"
    return "judgment"


def _stratified(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Proportional over (seat, cause, category) so no seat or error kind can
    dominate the sample the ceilings are read off."""
    buckets: dict[tuple, list] = defaultdict(list)
    for r in rows:
        buckets[(r["seat"], r["_cause"], r.get("category"))].append(r)
    rng = random.Random(seed)
    for b in buckets.values():
        rng.shuffle(b)
    picked, i = [], 0
    keys = sorted(buckets, key=lambda k: (-len(buckets[k]), str(k)))
    while len(picked) < n and any(buckets[k] for k in keys):
        k = keys[i % len(keys)]
        if buckets[k]:
            picked.append(buckets[k].pop())
        i += 1
    return picked[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=621)
    ap.add_argument("--debug-dir", type=Path, default=DEBUG_DIR)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    rows = _load(a.debug_dir)
    for r in rows:
        r["_cause"] = classify(r)
    bad = [r for r in rows if r["_cause"]]

    def ceilings(subset: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(subset)
        fs = [r for r in subset if (r.get("score") or {}).get("false_supported")]
        # "false gap" = a GAP/finding asserted where gold says none.
        fg = [
            r
            for r in subset
            if (r.get("score") or {}).get("pred") not in (None, r.get("gold_label"))
            and str((r.get("score") or {}).get("pred", "")).upper() != "SUPPORTED"
            and str(r.get("gold_label", "")).upper() == "SUPPORTED"
        ]
        return {
            "cases": n,
            "false_supported": len(fs),
            "false_supported_rate": round(len(fs) / n, 4) if n else None,
            "false_gap": len(fg),
            "false_gap_rate": round(len(fg) / n, 4) if n else None,
            "false_gap_ceiling_met": (len(fg) / n <= 0.10) if n else None,
        }

    roster_rows = [r for r in rows if r["seat"] in ROSTER]
    sample = _stratified(bad, a.sample, a.seed)

    # "Zero UNRESOLVED false-supported" is Y21's other bar. A case counts as
    # resolved when the resolutions file names its mechanism, its disposition
    # and the test that pins it — so a NEW false-supported case surfaces rather
    # than being absorbed into a rate.
    import yaml

    res_path = REPO / "config/compliance/y21_resolutions.yaml"
    resolutions = (
        (yaml.safe_load(res_path.read_text()) or {}).get("resolutions", {})
        if res_path.exists()
        else {}
    )
    roster_fs = sorted(
        {r.get("id") for r in roster_rows if (r.get("score") or {}).get("false_supported")}
    )
    unresolved = [c for c in roster_fs if c not in resolutions]

    result = {
        "source": str(a.debug_dir),
        "seats_swept": sorted({r["seat"] for r in rows}),
        "roster": sorted(ROSTER),
        "totals": {
            "case_rows": len(rows),
            "disagreements": len(bad),
            "disagreement_rate": round(len(bad) / len(rows), 4),
        },
        "cause_mix_all_seats": dict(Counter(r["_cause"] for r in bad).most_common()),
        "cause_mix_roster": dict(
            Counter(r["_cause"] for r in roster_rows if r["_cause"]).most_common()
        ),
        "ceilings_all_seats": ceilings(rows),
        "ceilings_roster": ceilings(roster_rows),
        "per_seat": {
            seat: {
                "cases": sum(1 for r in rows if r["seat"] == seat),
                "disagreements": sum(1 for r in bad if r["seat"] == seat),
                "causes": dict(
                    Counter(r["_cause"] for r in bad if r["seat"] == seat).most_common()
                ),
                **ceilings([r for r in rows if r["seat"] == seat]),
            }
            for seat in sorted({r["seat"] for r in rows})
        },
        "sample": [
            {
                "seat": r["seat"],
                "case": r.get("id"),
                "category": r.get("category"),
                "cause": r["_cause"],
                "gold_label": r.get("gold_label"),
                "pred": (r.get("score") or {}).get("pred"),
                "gold_citation": r.get("gold_citation"),
                "cited_refs": (r.get("parsed") or {}).get("cited_refs"),
                "packet_std_allowlist": r.get("packet_std_allowlist"),
                "false_supported": (r.get("score") or {}).get("false_supported"),
                "raw_head": (r.get("raw_response") or "")[:400],
            }
            for r in sample
        ],
        "sample_cause_mix": dict(Counter(r["_cause"] for r in sample).most_common()),
        "sample_seat_mix": dict(Counter(r["seat"] for r in sample).most_common()),
        "false_supported_cases_roster": roster_fs,
        "resolved_cases": sorted(resolutions),
        "unresolved_false_supported": unresolved,
        "resolutions": resolutions,
        "verdict_y21": (
            "PASS" if not unresolved and ceilings(roster_rows)["false_gap_ceiling_met"] else "FAIL"
        ),
    }

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2, default=str))

    t = result["totals"]
    print(
        f"case rows {t['case_rows']} | disagreements {t['disagreements']} "
        f"({t['disagreement_rate']:.1%})"
    )
    print(f"cause mix (all seats): {result['cause_mix_all_seats']}")
    print(f"cause mix (roster):    {result['cause_mix_roster']}")
    for label, key in (("ALL SEATS", "ceilings_all_seats"), ("ROSTER", "ceilings_roster")):
        c = result[key]
        print(
            f"{label:9} n={c['cases']:4} false_supported={c['false_supported']:3} "
            f"({c['false_supported_rate']:.1%})  false_gap={c['false_gap']:3} "
            f"({c['false_gap_rate']:.1%})  ceiling<=10%: "
            f"{'MET' if c['false_gap_ceiling_met'] else 'NOT MET'}"
        )
    print(f"stratified sample: {len(result['sample'])} rows, causes {result['sample_cause_mix']}")
    print(
        f"roster false_supported: {result['false_supported_cases_roster']} | "
        f"resolved: {result['resolved_cases']} | "
        f"UNRESOLVED: {result['unresolved_false_supported'] or 'none'}"
    )
    print(f"Y21 verdict: {result['verdict_y21']}")


if __name__ == "__main__":
    main()
