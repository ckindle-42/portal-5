#!/usr/bin/env python3
"""Y23 — aggregate the prompt-sensitivity sweep into an F2 range.

Reads the per-variant debug dirs `scripts/compliance_y23_run.sh` writes and
re-scores them with the probe's own scorer (`rescore_debug_dir` — verbatim raw
responses, no model calls), so this can be re-run after any scorer change and
costs seconds.

Y23's question is NOT "which wording wins". It is whether the headline F2 is a
property of the seat or of the sentence it was asked in: a range at or above
`--threshold` means the number is a prompt artifact and must be reported with
its range attached, never bare.

`outdated_rule` ADDS the OUTDATED_LANGUAGE trigger Y21 found missing rather than
rewording an existing rule, so it is reported separately and excluded from the
range — folding a deliberate behaviour change into a wording-noise measurement
would overstate the noise.

    uv run python scripts/compliance_y23_aggregate.py --out <path>.json
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

probe = importlib.import_module("tests.benchmarks.bench_judgment_probe_v6")

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "coding_task/v9_compliance/private/runs/D0_20260906T185401Z"
DEBUG_ROOT = RUN / "y23_debug"
NOT_A_PARAPHRASE = {"outdated_rule"}
EXPECTED_LINES = 31  # 1 preflight + 30 cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug-root", type=Path, default=DEBUG_ROOT)
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    variants: dict[str, dict[str, float]] = {}
    incomplete: list[str] = []
    for vdir in sorted(p for p in a.debug_root.iterdir() if p.is_dir()):
        for f in vdir.glob("*.debug.jsonl"):
            n = sum(1 for line in f.read_text().splitlines() if line.strip())
            if n < EXPECTED_LINES:
                incomplete.append(f"{vdir.name}/{f.stem} ({n}/{EXPECTED_LINES} rows)")
        rows = probe.rescore_debug_dir(vdir)
        variants[vdir.name] = {
            r["model"]: r["aggregate"]["F2_violation"] for r in rows if r.get("model")
        }

    seats = sorted({m for v in variants.values() for m in v})
    paraphrases = [v for v in variants if v not in NOT_A_PARAPHRASE]

    per_seat = {}
    for seat in seats:
        vals = {v: variants[v].get(seat) for v in paraphrases}
        got = [x for x in vals.values() if x is not None]
        if not got:
            continue
        per_seat[seat] = {
            "by_variant": vals,
            "f2_min": min(got),
            "f2_max": max(got),
            "f2_range": round(max(got) - min(got), 4),
            "f2_mean": round(sum(got) / len(got), 4),
            "non_paraphrase": {v: variants[v].get(seat) for v in variants if v in NOT_A_PARAPHRASE},
        }

    ranges = [v["f2_range"] for v in per_seat.values()]
    maxr = max(ranges) if ranges else None
    summary = {
        "paraphrase_variants": sorted(paraphrases),
        "non_paraphrase_variants": sorted(v for v in variants if v in NOT_A_PARAPHRASE),
        "seats": seats,
        "per_seat": per_seat,
        "max_f2_range_across_roster": maxr,
        "artifact_threshold": a.threshold,
        "incomplete_pairs": incomplete,
        "complete": not incomplete
        and len(paraphrases) >= 4
        and all(len(v) == len(seats) for v in variants.values()),
        "verdict": (
            None
            if maxr is None
            else ("PROMPT_ARTIFACT" if maxr >= a.threshold else "STABLE_UNDER_PARAPHRASE")
        ),
    }

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(summary, indent=2))

    print(f"variants: {sorted(variants)}")
    for seat, v in per_seat.items():
        print(
            f"{seat[:50]:52} F2 {v['f2_min']:.3f}-{v['f2_max']:.3f} "
            f"(range {v['f2_range']:.3f}, mean {v['f2_mean']:.3f})  "
            f"non-paraphrase {v['non_paraphrase']}"
        )
    if incomplete:
        print(f"INCOMPLETE pairs: {incomplete}")
    print(f"max range across roster: {maxr} (threshold {a.threshold})")
    print(f"verdict: {summary['verdict']}  complete: {summary['complete']}")


if __name__ == "__main__":
    main()
