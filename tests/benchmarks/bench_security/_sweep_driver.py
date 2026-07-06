"""Driver for the agentic blue eval sweep (arms x models x scenarios x N trials).

M2: multi-trial support — reports pass@k (found in >=1 trial) AND mean±stdev.
Classifies each cell: reliable (k/k), unreliable (partial), incapable (0/k).

M5: auto-writes the winning (model, arm, config) as a cited wiki unit.

Run directly: python3 -m tests.benchmarks.bench_security._sweep_driver
Env vars:
    TRIALS=N        number of trials per cell (default 3)
    SWEEP_SCENARIOS comma-separated scenario list (overrides defaults)
    SWEEP_MODELS    comma-separated model list (overrides defaults)
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

from tests.benchmarks.bench_security.agentic_blue_eval import run_eval

MODELS = ["granite4.1:8b-ctx8k", "gpt-oss:20b", "huihui_ai/qwen3.5-abliterated:9b"]
SCENARIOS = ["kerberoast_to_da", "asrep_to_lateral", "meta3_ftp_backdoor"]
ARMS = ["raw", "tools", "harness"]

OUT_PATH = Path("/tmp/agentic_blue_sweep.json")


def _get_trials() -> int:
    """Get trial count from env, default 3."""
    return int(os.environ.get("TRIALS", "3"))


def _classify_cell(pass_count: int, total: int) -> str:
    """Classify a cell's reliability: reliable / unreliable / incapable."""
    if pass_count == total:
        return "reliable"
    if pass_count == 0:
        return "incapable"
    return "unreliable"


def _mean_stdev(values: list[float]) -> tuple[float, float]:
    """Compute mean and population stdev."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _aggregate_trials(trial_results: list[dict]) -> dict:
    """Aggregate N trial results into pass@k, mean±stdev, and tiered scores.

    Each trial_result is a run_eval() output dict with 'arms' keyed by arm name.
    """
    n = len(trial_results)
    if n == 0:
        return {}

    # Collect arm names from first trial
    arm_names = list(trial_results[0].get("arms", {}).keys())

    aggregated: dict[str, dict] = {}
    for arm in arm_names:
        arm_trials = []
        for tr in trial_results:
            arm_data = tr.get("arms", {}).get(arm, {})
            arm_trials.append(arm_data)

        # Collect per-tier recall values across trials
        exact_recalls = []
        parent_recalls = []
        tactic_recalls = []
        overall_recalls = []
        pass_count_exact = 0
        pass_count_parent = 0
        pass_count_tactic = 0
        pass_count_overall = 0

        for at in arm_trials:
            tiered = at.get("tiered", {})
            exact_r = tiered.get("exact", {}).get("recall", 0.0)
            parent_r = tiered.get("parent", {}).get("recall", 0.0)
            tactic_r = tiered.get("tactic", {}).get("recall", 0.0)
            overall_r = tiered.get("overall", {}).get("recall", 0.0)

            exact_recalls.append(exact_r)
            parent_recalls.append(parent_r)
            tactic_recalls.append(tactic_r)
            overall_recalls.append(overall_r)

            if exact_r > 0:
                pass_count_exact += 1
            if parent_r > 0:
                pass_count_parent += 1
            if tactic_r > 0:
                pass_count_tactic += 1
            if overall_r > 0:
                pass_count_overall += 1

        exact_mean, exact_std = _mean_stdev(exact_recalls)
        parent_mean, parent_std = _mean_stdev(parent_recalls)
        tactic_mean, tactic_std = _mean_stdev(tactic_recalls)
        overall_mean, overall_std = _mean_stdev(overall_recalls)

        aggregated[arm] = {
            "trials": n,
            "tiered_summary": {
                "exact": {
                    "pass_at_k": pass_count_exact,
                    "pass_rate": round(pass_count_exact / n, 3) if n else 0.0,
                    "mean_recall": round(exact_mean, 3),
                    "stdev_recall": round(exact_std, 3),
                    "per_trial": [round(r, 3) for r in exact_recalls],
                    "classification": _classify_cell(pass_count_exact, n),
                },
                "parent": {
                    "pass_at_k": pass_count_parent,
                    "pass_rate": round(pass_count_parent / n, 3) if n else 0.0,
                    "mean_recall": round(parent_mean, 3),
                    "stdev_recall": round(parent_std, 3),
                    "per_trial": [round(r, 3) for r in parent_recalls],
                    "classification": _classify_cell(pass_count_parent, n),
                },
                "tactic": {
                    "pass_at_k": pass_count_tactic,
                    "pass_rate": round(pass_count_tactic / n, 3) if n else 0.0,
                    "mean_recall": round(tactic_mean, 3),
                    "stdev_recall": round(tactic_std, 3),
                    "per_trial": [round(r, 3) for r in tactic_recalls],
                    "classification": _classify_cell(pass_count_tactic, n),
                },
                "overall": {
                    "pass_at_k": pass_count_overall,
                    "pass_rate": round(pass_count_overall / n, 3) if n else 0.0,
                    "mean_recall": round(overall_mean, 3),
                    "stdev_recall": round(overall_std, 3),
                    "per_trial": [round(r, 3) for r in overall_recalls],
                    "classification": _classify_cell(pass_count_overall, n),
                },
            },
            # Keep the last trial's detail for inspection
            "last_trial": arm_trials[-1] if arm_trials else {},
        }

    return aggregated


def _compute_arm_deltas(results: list[dict]) -> dict[str, dict]:
    """Compute per-model arm-vs-arm deltas across all scenarios.

    For each model, aggregates mean_recall per tier across scenarios,
    then computes harness−raw and harness−tools deltas.

    Returns {model: {tier: {raw, tools, harness, delta_raw, delta_tools}}}.
    """
    # Group results by model
    by_model: dict[str, list[dict]] = {}
    for r in results:
        model = r.get("model", "")
        by_model.setdefault(model, []).append(r)

    deltas: dict[str, dict] = {}
    for model, model_results in by_model.items():
        # Average mean_recall across scenarios for each arm+tier
        arm_tier_sums: dict[str, dict[str, list[float]]] = {}
        for r in model_results:
            for arm_name, arm_data in r.get("arms", {}).items():
                ts = arm_data.get("tiered_summary", {})
                arm_tier_sums.setdefault(arm_name, {})
                for tier in ["exact", "parent", "tactic"]:
                    arm_tier_sums[arm_name].setdefault(tier, [])
                    arm_tier_sums[arm_name][tier].append(ts.get(tier, {}).get("mean_recall", 0.0))

        # Compute averages
        model_tiers: dict[str, dict] = {}
        for tier in ["exact", "parent", "tactic"]:
            raw_vals = arm_tier_sums.get("raw", {}).get(tier, [0.0])
            tools_vals = arm_tier_sums.get("tools", {}).get(tier, [0.0])
            harness_vals = arm_tier_sums.get("harness", {}).get(tier, [0.0])

            raw_mr = sum(raw_vals) / len(raw_vals) if raw_vals else 0.0
            tools_mr = sum(tools_vals) / len(tools_vals) if tools_vals else 0.0
            harness_mr = sum(harness_vals) / len(harness_vals) if harness_vals else 0.0

            model_tiers[tier] = {
                "raw": round(raw_mr, 3),
                "tools": round(tools_mr, 3),
                "harness": round(harness_mr, 3),
                "delta_raw": round(harness_mr - raw_mr, 3),
                "delta_tools": round(harness_mr - tools_mr, 3),
            }

        deltas[model] = model_tiers

    return deltas


def _write_back_winning_config(results: list[dict]) -> str | None:
    """M5: Write arm-vs-arm delta report as a cited wiki unit.

    Reports per-model harness−raw / harness−tools deltas per tier.
    Proposes seat config ONLY from the harness arm (production config).
    Flags harness<raw as an explicit red flag.

    Returns the proposed unit ID, or None if writeback failed.
    """
    if not results:
        return None

    n_trials = results[0].get("_trials", 1)
    scenarios = sorted({r.get("scenario", "") for r in results})
    sweep_date = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())

    deltas = _compute_arm_deltas(results)

    # Find best harness-arm cell for seat config proposal
    best_harness_score = -1.0
    best_harness_model = ""

    # Track red flags (harness < raw)
    red_flags: list[str] = []

    body_lines = [
        "# Agentic Blue Eval — Arm-vs-Arm Delta Report",
        "",
        f"**Trials per cell:** {n_trials}  ",
        f"**Scenarios:** {', '.join(scenarios)}  ",
        f"**Sweep date:** {sweep_date}",
        "",
        "## Per-Model Arm Deltas (the harness-contribution number)",
        "",
        "The three-arm design exists to answer: **does the harness beat raw, for the same model, "
        "and by how much?** The delta `harness−raw` is the harness contribution.",
        "",
    ]

    for model, model_tiers in sorted(deltas.items()):
        body_lines.append(f"### `{model}`")
        body_lines.append("")
        body_lines.append("| Tier | raw | tools | harness | harness−raw | harness−tools |")
        body_lines.append("|------|-----|-------|---------|-------------|---------------|")

        for tier in ["exact", "parent", "tactic"]:
            t = model_tiers[tier]
            raw_s = f"{t['raw']:.3f}"
            tools_s = f"{t['tools']:.3f}"
            harness_s = f"{t['harness']:.3f}"

            # Format deltas with sign and flag
            dr = t["delta_raw"]
            dt = t["delta_tools"]
            delta_raw_s = f"+{dr:.3f}" if dr >= 0 else f"{dr:.3f}"
            delta_tools_s = f"+{dt:.3f}" if dt >= 0 else f"{dt:.3f}"

            if dr < 0:
                delta_raw_s += " RED-FLAG"
                red_flags.append(f"{model}/{tier}: harness={t['harness']:.3f} < raw={t['raw']:.3f}")

            body_lines.append(
                f"| {tier} | {raw_s} | {tools_s} | {harness_s} | {delta_raw_s} | {delta_tools_s} |"
            )

        body_lines.append("")

        # Score this model's harness arm for seat config selection
        h = model_tiers
        harness_score = (
            h["exact"]["harness"] * 2.0
            + h["parent"]["harness"] * 1.5
            + h["tactic"]["harness"] * 1.0
        )
        if harness_score > best_harness_score:
            best_harness_score = harness_score
            best_harness_model = model

    # Red flags section
    if red_flags:
        body_lines.extend(
            [
                "## RED FLAGS (harness < raw)",
                "",
                "These cells show the harness underperforming raw — possible arm-wiring bug or harness regression:",
                "",
            ]
        )
        for rf in red_flags:
            body_lines.append(f"- {rf}")
        body_lines.append("")

    # Recommended seat config (harness arm only)
    if best_harness_model:
        body_lines.extend(
            [
                "## Recommended Seat Config",
                "",
                f"**Model:** `{best_harness_model}`  ",
                "**Arm:** harness (production config — raw/tools are ablations, never deployed)",
                "",
            ]
        )

        body_lines.append(f"| Tier | harness recall | pass@{n_trials} |")
        body_lines.append("|------|---------------|---------|")
        for tier in ["exact", "parent", "tactic"]:
            # Get per-scenario pass@k for this model's harness arm
            harness_pass_k = []
            harness_recalls = []
            for r in results:
                if r.get("model") != best_harness_model:
                    continue
                h_data = r.get("arms", {}).get("harness", {}).get("tiered_summary", {})
                harness_pass_k.append(h_data.get(tier, {}).get("pass_at_k", 0))
                harness_recalls.append(h_data.get(tier, {}).get("mean_recall", 0))

            avg_recall = sum(harness_recalls) / len(harness_recalls) if harness_recalls else 0
            total_pass = sum(harness_pass_k)
            total_possible = len(harness_pass_k) * n_trials
            body_lines.append(f"| {tier} | {avg_recall:.3f} | {total_pass}/{total_possible} |")
        body_lines.append("")

    body = "\n".join(body_lines)

    # Print delta summary to stdout
    print("\n" + "=" * 90)
    print("ARM-VS-ARM DELTAS (harness contribution)")
    print("=" * 90)
    for model, model_tiers in sorted(deltas.items()):
        print(f"\n{model}:")
        print(
            f"  {'Tier':8s} | {'raw':>6s} | {'tools':>6s} | {'harness':>7s} | {'h-raw':>7s} | {'h-tools':>7s}"
        )
        print(f"  {'-' * 8}-+-{'-' * 6}-+-{'-' * 6}-+-{'-' * 7}-+-{'-' * 7}-+-{'-' * 7}")
        for tier in ["exact", "parent", "tactic"]:
            t = model_tiers[tier]
            dr = t["delta_raw"]
            dt = t["delta_tools"]
            flag = " RED-FLAG" if dr < 0 else ""
            print(
                f"  {tier:8s} | {t['raw']:>6.3f} | {t['tools']:>6.3f} | {t['harness']:>7.3f} | "
                f"{dr:>+7.3f} | {dt:>+7.3f}{flag}"
            )

    if red_flags:
        print("\nRED FLAGS:")
        for rf in red_flags:
            print(f"  ! {rf}")

    if best_harness_model:
        print(f"\nRecommended seat: {best_harness_model} (harness arm)")

    # Write wiki unit
    try:
        from portal_wiki.core.writeback import propose_unit

        unit_id = f"SEC_BENCH-agentic-blue-deltas-{time.strftime('%Y%m%d', time.gmtime())}"
        tags = ["agentic-blue", "maturation", "arm-deltas"]
        for model in deltas:
            tags.append(model.replace(":", "-"))

        proposed = propose_unit(
            {
                "id": unit_id,
                "title": f"Agentic Blue Arm Deltas: harness contribution ({sweep_date})",
                "kind": "what",
                "body": body,
                "sources": [
                    {
                        "type": "bench-security",
                        "path": str(OUT_PATH),
                        "description": f"Agentic blue eval sweep ({n_trials} trials, {len(scenarios)} scenarios)",
                    }
                ],
                "tags": tags,
            },
            proposed_by="sec-maturation-sweep",
            auto_confirm=True,
        )
        print(f"M5: Delta report written to wiki: {proposed.unit_id} (status={proposed.status})")
        return proposed.unit_id
    except Exception as exc:
        print(f"M5: Write-back failed (non-fatal): {exc}")
        return None


def main() -> None:
    trials = _get_trials()

    # Allow env overrides for scenarios and models
    scenarios = SCENARIOS
    if os.environ.get("SWEEP_SCENARIOS"):
        scenarios = [s.strip() for s in os.environ["SWEEP_SCENARIOS"].split(",")]
    models = MODELS
    if os.environ.get("SWEEP_MODELS"):
        models = [m.strip() for m in os.environ["SWEEP_MODELS"].split(",")]

    # Support --all-captured flag (M3: scale sweep)
    import sys

    if "--all-captured" in sys.argv:
        try:
            from tests.benchmarks.bench_security.exec_chain import SCENARIOS as ALL_SCENARIOS
            from tests.benchmarks.bench_security.siem.capture_store import list_captures

            available = [s for s in ALL_SCENARIOS if list_captures(s)]
            if available:
                scenarios = available
                print(f"--all-captured: found {len(scenarios)} scenarios with captures")
            else:
                print("--all-captured: no captures found, using defaults")
        except Exception as exc:
            print(f"--all-captured: failed to discover captures ({exc}), using defaults")

    # Check for --scenarios flag
    for arg in sys.argv:
        if arg.startswith("--scenarios="):
            scenarios = [s.strip() for s in arg.split("=", 1)[1].split(",")]

    print(f"Sweep config: {len(scenarios)} scenarios x {len(models)} models x {trials} trials")
    print(f"Scenarios: {scenarios}")
    print(f"Models: {models}")
    print(f"Output: {OUT_PATH}")
    print()

    # Load existing results (supports incremental runs)
    results: list[dict] = []
    if OUT_PATH.exists():
        results = json.loads(OUT_PATH.read_text())

    # Build set of already-completed (scenario, model) pairs with enough trials
    completed = set()
    for r in results:
        key = (r.get("scenario"), r.get("model"))
        trial_count = r.get("_trials", 1)
        if trial_count >= trials:
            completed.add(key)

    total = len(scenarios) * len(models)
    i = 0
    for scenario in scenarios:
        for model in models:
            i += 1
            if (scenario, model) in completed:
                print(f"[{i}/{total}] SKIP (already done) {scenario} x {model}")
                continue

            print(
                f"[{i}/{total}] RUNNING {scenario} x {model} ({trials} trials) ...",
                flush=True,
            )
            t0 = time.monotonic()

            trial_results = []
            for trial_i in range(trials):
                print(f"  trial {trial_i + 1}/{trials} ...", flush=True)
                result = run_eval(scenario, model=model, arms=ARMS)
                trial_results.append(result)

            # Aggregate across trials
            aggregated = _aggregate_trials(trial_results)
            wall_s = round(time.monotonic() - t0, 1)

            # Build output record
            record = {
                "scenario": scenario,
                "model": model,
                "_trials": trials,
                "_wall_s": wall_s,
                "ground_truth": trial_results[0].get("ground_truth", []),
                "arms": aggregated,
            }

            # Remove any previous result for this (scenario, model) with fewer trials
            results = [
                r
                for r in results
                if (r.get("scenario"), r.get("model")) != (scenario, model)
                or r.get("_trials", 1) >= trials
            ]
            results.append(record)
            OUT_PATH.write_text(json.dumps(results, indent=2))

            # Print summary
            for arm_name, arm_data in aggregated.items():
                ts = arm_data.get("tiered_summary", {})
                exact_cls = ts.get("exact", {}).get("classification", "?")
                parent_cls = ts.get("parent", {}).get("classification", "?")
                tactic_cls = ts.get("tactic", {}).get("classification", "?")
                exact_mr = ts.get("exact", {}).get("mean_recall", 0)
                parent_mr = ts.get("parent", {}).get("mean_recall", 0)
                tactic_mr = ts.get("tactic", {}).get("mean_recall", 0)
                print(
                    f"  {arm_name}: exact={exact_mr:.3f}({exact_cls}) "
                    f"parent={parent_mr:.3f}({parent_cls}) "
                    f"tactic={tactic_mr:.3f}({tactic_cls})"
                )

            print(
                f"[{i}/{total}] DONE {scenario} x {model} in {wall_s}s",
                flush=True,
            )

    # Final summary table
    print("\n" + "=" * 80)
    print("SWEEP SUMMARY")
    print("=" * 80)
    for r in results:
        scenario = r.get("scenario", "?")
        model = r.get("model", "?")
        n_trials = r.get("_trials", 1)
        print(f"\n{scenario} x {model} ({n_trials} trials):")
        for arm_name, arm_data in r.get("arms", {}).items():
            ts = arm_data.get("tiered_summary", {})
            print(
                f"  {arm_name:10s} | "
                f"exact: pass@{n_trials}={ts.get('exact', {}).get('pass_at_k', 0)}/{n_trials} "
                f"mean={ts.get('exact', {}).get('mean_recall', 0):.3f} "
                f"[{ts.get('exact', {}).get('classification', '?'):11s}] | "
                f"parent: pass@{n_trials}={ts.get('parent', {}).get('pass_at_k', 0)}/{n_trials} "
                f"mean={ts.get('parent', {}).get('mean_recall', 0):.3f} "
                f"[{ts.get('parent', {}).get('classification', '?'):11s}] | "
                f"tactic: pass@{n_trials}={ts.get('tactic', {}).get('pass_at_k', 0)}/{n_trials} "
                f"mean={ts.get('tactic', {}).get('mean_recall', 0):.3f} "
                f"[{ts.get('tactic', {}).get('classification', '?'):11s}]"
            )

    print(f"\nSweep complete: {len(results)} results written to {OUT_PATH}")

    # M5: Write winning config back to wiki
    if results:
        unit_id = _write_back_winning_config(results)
        if unit_id:
            print(f"M5: Wiki unit: {unit_id}")


if __name__ == "__main__":
    main()
