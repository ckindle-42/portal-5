#!/usr/bin/env python3
"""Compare CAD gauntlet v2 runs: summary, per-task PASS, why cells failed, routing.

Usage: python tests/benchmarks/compare_cad_gauntlet.py LABEL [LABEL ...] [--out FILE.md]
LABEL is the --label given to bench_cad_gauntlet_v2.py (the newest matching result file is used).
Gate (TASK_CAD_ARM_REDEVELOP_V1 P5): an arm ships iff mean_score >= baseline AND validity >= baseline;
the first LABEL is the baseline.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
TASKS = [
    "plate_4holes",
    "grommet_plate",
    "enclosure",
    "l_bracket",
    "flanged_bushing",
    "countersunk_plate",
    "hex_standoff",
    "spur_gear",
]


def load(label: str) -> dict:
    files = sorted(glob.glob(str(RESULTS / f"cad_gauntlet_v2_{label}_*.json")))
    if not files:
        raise SystemExit(f"no result file for label {label!r}")
    return json.loads(Path(files[-1]).read_text())["arms"][0]


def stats(cells: list[dict]) -> dict:
    n = len(cells)
    return {
        "n": n,
        "mean": statistics.mean(c["score"] for c in cells),
        "pass": sum(c["verdict"] == "PASS" for c in cells),
        "validity": sum(c["verdict"] in ("PASS", "WRONGSIZE") for c in cells) / n,
        "median_s": statistics.median(c["elapsed_s"] for c in cells),
        "capped": sum(c.get("ended") == "turn_cap" for c in cells),
    }


def render(labels: list[str]) -> str:
    arms = {label: load(label) for label in labels}
    out = ["# CAD gauntlet v2 comparison", "", f"Baseline: `{labels[0]}`", ""]
    out += [
        "| label | model | cells | mean | PASS | validity | median s | turn cap | gate vs baseline |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    base = stats(arms[labels[0]]["cells"])
    for label, arm in arms.items():
        s = stats(arm["cells"])
        gate = (
            "baseline"
            if label == labels[0]
            else (
                "PASS"
                if s["mean"] >= base["mean"] and s["validity"] >= base["validity"]
                else "FAIL"
            )
        )
        out.append(
            f"| {label} | `{arm['model']}` | {s['n']} | {s['mean']:.3f} | {s['pass']} | "
            f"{s['validity']:.2f} | {s['median_s']:.0f} | {s['capped']} | {gate} |"
        )
    out += ["", "## Per task (PASS / cells)", "", "| task | " + " | ".join(labels) + " |"]
    out.append("|---|" + "---|" * len(labels))
    for t in TASKS:
        row = []
        for label in labels:
            cs = [c for c in arms[label]["cells"] if c["task"] == t]
            row.append(f"{sum(c['verdict'] == 'PASS' for c in cs)}/{len(cs)}" if cs else "-")
        out.append(f"| {t} | " + " | ".join(row) + " |")
    out += ["", "## Why cells did not PASS (failed grader checks / ended)", ""]
    for label, arm in arms.items():
        fails = collections.Counter()
        for c in arm["cells"]:
            if c["verdict"] == "WRONGSIZE":
                fails[("WRONGSIZE: " + "+".join(k for k, v in c["checks"].items() if not v))] += 1
            elif c["verdict"] != "PASS":
                fails[f"{c['verdict']} ended={c.get('ended')}"] += 1
        out.append(
            f"- **{label}**: "
            + (", ".join(f"{k} x{v}" for k, v in fails.most_common()) or "all PASS")
        )
    out += ["", "## First tool chosen per task (routing)", ""]
    for label, arm in arms.items():
        first: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for c in arm["cells"]:
            if c["tool_calls"]:
                first[c["task"]][c["tool_calls"][0]["tool"]] += 1
        cells = "; ".join(
            f"{t}: " + "/".join(f"{k}x{v}" for k, v in first[t].items())
            for t in TASKS
            if t in first
        )
        out.append(f"- **{label}**: {cells}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    text = render(args.labels)
    if args.out:
        args.out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
