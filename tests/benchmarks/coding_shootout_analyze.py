#!/usr/bin/env python3
"""Portal 5 — Coding Shootout Analyzer.

Reads a JSON file produced by tests/portal5_persona_matrix.py for the
auto-coding-bench workspace, computes Pareto frontier (pass-rate x TPS x
memory), and prints a decision verdict per TASK_CODING_SHOOTOUT_V1 §A6.

Usage:
    python3 tests/benchmarks/coding_shootout_analyze.py \
        --input  tests/benchmarks/results/persona_matrix_auto-coding-bench_<UTC>.json \
        --output tests/benchmarks/results/coding_shootout_<UTC>.md

Decision rule (codified, not negotiable in this script):
  A candidate DEFEATS the incumbent Laguna-XS.2-4bit only if:
    1. assertion_pass_rate(candidate) >= assertion_pass_rate(incumbent) + 0.10
       AND
    2. tps_median(candidate) >= 0.75 * tps_median(incumbent)
  If multiple candidates qualify: lowest memory_gb wins (tiebreak).
  If none qualifies: verdict = INCONCLUSIVE; downstream repin task does
  not run.

Output: markdown summary with the table, the Pareto plot data, the
verdict, and the recommended next action.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

INCUMBENT_MODEL_ID = "mlx-community/Laguna-XS.2-4bit"

# Memory profiles read from backends.yaml — hardcoded here to avoid
# coupling the analyzer to the live config. If a candidate is added,
# update this dict and the candidate list in the task file.
MODEL_MEMORY_GB = {
    "mlx-community/Laguna-XS.2-4bit": 19,
    "mlx-community/GLM-4.7-Flash-4bit": 15,
    "mlx-community/Qwen3-Coder-30B-A3B-Instruct-8bit": 22,
    "lmstudio-community/Devstral-Small-2507-MLX-4bit": 15,
}

# Decision-rule thresholds. Conservative on purpose — small wins on a
# 5-scenario suite could be noise; the 10-pp gate forces a clearly-
# better candidate.
PASS_RATE_DELTA_THRESHOLD = 0.10
TPS_RATIO_THRESHOLD = 0.75


def load_matrix_results(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def summarize_per_model(report: dict) -> dict[str, dict]:
    """Aggregate matrix cells into per-model stats.

    Returns: {model_id: {pass_rate, n_scenarios, n_assertions, tps_median, tps_runs}}
    Matrix report shape: {cells: [{model, persona_slug, scenarios: [{results: [{passed: bool}]}], tps?: float}]}
    """
    per_model: dict[str, dict] = {}
    for cell in report.get("cells", []):
        model = cell.get("model") or cell.get("model_id") or ""
        if not model:
            continue
        entry = per_model.setdefault(
            model,
            {
                "n_scenarios": 0,
                "n_assertions": 0,
                "n_passed": 0,
                "tps_samples": [],
            },
        )
        for sc in cell.get("scenarios", []):
            entry["n_scenarios"] += 1
            for a in sc.get("results", []):
                entry["n_assertions"] += 1
                if a.get("passed"):
                    entry["n_passed"] += 1
            tps = sc.get("tps")
            if isinstance(tps, (int, float)) and tps > 0:
                entry["tps_samples"].append(float(tps))

    out: dict[str, dict] = {}
    for model, e in per_model.items():
        pass_rate = (e["n_passed"] / e["n_assertions"]) if e["n_assertions"] else 0.0
        tps_med = statistics.median(e["tps_samples"]) if e["tps_samples"] else 0.0
        out[model] = {
            "pass_rate": pass_rate,
            "n_scenarios": e["n_scenarios"],
            "n_assertions": e["n_assertions"],
            "n_passed": e["n_passed"],
            "tps_median": tps_med,
            "tps_runs": len(e["tps_samples"]),
            "memory_gb": MODEL_MEMORY_GB.get(model, 0),
        }
    return out


def decide(per_model: dict[str, dict]) -> dict:
    """Apply the decision rule. Returns a verdict dict."""
    incumbent = per_model.get(INCUMBENT_MODEL_ID)
    if not incumbent:
        return {
            "verdict": "INCONCLUSIVE",
            "reason": f"incumbent {INCUMBENT_MODEL_ID} not in results — "
                      "shootout must include it as control",
        }

    inc_pr = incumbent["pass_rate"]
    inc_tps = incumbent["tps_median"]
    if inc_tps <= 0:
        return {
            "verdict": "INCONCLUSIVE",
            "reason": "incumbent TPS unmeasured — cannot apply 75% ratio rule",
        }

    qualifiers = []
    for model, m in per_model.items():
        if model == INCUMBENT_MODEL_ID:
            continue
        pr_delta = m["pass_rate"] - inc_pr
        tps_ratio = m["tps_median"] / inc_tps if inc_tps else 0
        if (
            pr_delta >= PASS_RATE_DELTA_THRESHOLD
            and tps_ratio >= TPS_RATIO_THRESHOLD
        ):
            qualifiers.append({
                "model": model,
                "pr_delta": pr_delta,
                "tps_ratio": tps_ratio,
                "memory_gb": m["memory_gb"],
            })

    if not qualifiers:
        return {
            "verdict": "INCONCLUSIVE",
            "reason": (
                f"no candidate beat incumbent by >= {PASS_RATE_DELTA_THRESHOLD*100:.0f}pp "
                f"pass-rate while staying within {(1-TPS_RATIO_THRESHOLD)*100:.0f}% TPS"
            ),
            "incumbent_pass_rate": inc_pr,
            "incumbent_tps": inc_tps,
        }

    # Tiebreaker: lowest memory_gb wins
    qualifiers.sort(key=lambda q: (q["memory_gb"], -q["pr_delta"]))
    winner = qualifiers[0]
    return {
        "verdict": "REPIN_RECOMMENDED",
        "winner": winner["model"],
        "pass_rate_delta_pp": round(winner["pr_delta"] * 100, 1),
        "tps_ratio": round(winner["tps_ratio"], 2),
        "memory_gb": winner["memory_gb"],
        "alternatives": [q["model"] for q in qualifiers[1:]],
        "incumbent_pass_rate": inc_pr,
        "incumbent_tps": inc_tps,
    }


def render_markdown(per_model: dict[str, dict], verdict: dict, source: Path) -> str:
    lines: list[str] = []
    lines.append("# Coding Shootout — Results Summary")
    lines.append("")
    lines.append(f"**Source matrix run**: `{source.name}`")
    lines.append(f"**Decision rule**: candidate defeats incumbent iff "
                 f"pass-rate +>= {PASS_RATE_DELTA_THRESHOLD*100:.0f}pp AND "
                 f"TPS ratio >= {TPS_RATIO_THRESHOLD:.2f}x incumbent.")
    lines.append("")
    lines.append("## Per-Model Aggregate")
    lines.append("")
    lines.append("| Model | Pass-rate | Passed/Total | TPS (median) | Memory GB |")
    lines.append("|---|---|---|---|---|")
    order = sorted(per_model.items(), key=lambda kv: -kv[1]["pass_rate"])
    for model, m in order:
        marker = "  incumbent" if model == INCUMBENT_MODEL_ID else ""
        lines.append(
            f"| `{model}`{marker} | "
            f"{m['pass_rate']*100:.1f}% | "
            f"{m['n_passed']}/{m['n_assertions']} | "
            f"{m['tps_median']:.1f} | "
            f"{m['memory_gb']} |"
        )
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict['verdict']}**")
    lines.append("")
    if verdict["verdict"] == "REPIN_RECOMMENDED":
        lines.append(f"- Winner: `{verdict['winner']}`")
        lines.append(f"- Pass-rate delta vs incumbent: +{verdict['pass_rate_delta_pp']} pp")
        lines.append(f"- TPS ratio vs incumbent: {verdict['tps_ratio']}x")
        lines.append(f"- Memory: {verdict['memory_gb']} GB")
        if verdict.get("alternatives"):
            lines.append(f"- Alternates also qualified: {verdict['alternatives']}")
        lines.append("")
        lines.append("**Next action**: produce `TASK_AUTO_CODING_REPIN_V1.md` to swap "
                     f"`auto-coding` `mlx_model_hint` from "
                     f"`{INCUMBENT_MODEL_ID}` -> `{verdict['winner']}`. "
                     "Re-run UAT Phase 3 post-swap to confirm pass-rate recovery.")
    else:
        lines.append(f"Reason: {verdict.get('reason', '(unspecified)')}")
        lines.append("")
        lines.append("**Next action**: no repin. Incumbent stays. If new candidate "
                     "models become available (or the scenario set is broadened), "
                     "re-run this shootout.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", required=True, type=Path,
                    help="persona_matrix_auto-coding-bench_<UTC>.json")
    ap.add_argument("--output", required=True, type=Path,
                    help="markdown summary destination")
    args = ap.parse_args(argv)

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2

    report = load_matrix_results(args.input)
    per_model = summarize_per_model(report)
    if not per_model:
        print("no per-model data extracted — check matrix JSON shape", file=sys.stderr)
        return 3

    verdict = decide(per_model)
    md = render_markdown(per_model, verdict, args.input)
    args.output.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
