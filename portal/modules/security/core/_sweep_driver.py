"""Driver for the agentic blue eval sweep (arms x models x scenarios x N trials).

M2: multi-trial support — reports pass@k (found in >=1 trial) AND mean±stdev.
Classifies each cell: reliable (k/k), unreliable (partial), incapable (0/k).

M5: auto-writes the winning (model, arm, config) as a cited wiki unit.

Parallel: ThreadPoolExecutor at the cell level (scenario × model).
Each cell's trials run serially (trials are dependent — same model/scenario).

CAVEAT (verified 2026-07-07): OLLAMA_NUM_PARALLEL=4 gives real concurrent
throughput for short/decode-bound prompts (confirmed 2-3.8x on trivial
prompts), but this bench's payloads (system prompt + telemetry preview,
~7-8k tokens per initial turn) are prefill-dominated — a single raw call
profiled at prompt_eval_duration=25.8s vs eval_duration=3.7s (87% prefill).
Prefill is compute-bound on one Metal GPU: concurrent cells with DIFFERENT
scenarios (different telemetry, no shared prefix) measured at ~1x wall-clock
per worker (fully additive, not overlapped) — e.g. 2 concurrent unique
7500-token calls took wall=63.6s vs 31.9s solo. SWEEP_WORKERS>1 does NOT
give proportional speedup on the full/decision sweep; treat call-count
reduction (TRIALS, --arms, --sample, --step-cap below) as the primary lever,
not worker count. Ollama DOES automatically cache the repeated initial
prefix within a cell (trial 0 cold ~12s -> trials 1+ ~2.5s, same
scenario+model) — free, no code change needed, but it only covers the first
turn; tool-loop turns after that diverge per trial (sampling) and are never
cacheable.

Run directly: python3 -m portal.modules.security.core._sweep_driver
Env vars:
    TRIALS=N        number of trials per cell (default 3)
    SWEEP_SCENARIOS comma-separated scenario list (overrides defaults)
    SWEEP_MODELS    comma-separated model list (overrides defaults)
    SWEEP_WORKERS=N parallel workers (default 4; real gain is limited — see
                    CAVEAT above; helps most when cells are short/raw-arm-only)
CLI flags:
    --all-captured  run across all scenarios with local captures
    --scenarios=X,Y run only specified scenarios
    --arms=X,Y      run only specified arms (e.g. harness,raw for fast iteration)
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from portal.modules.security.core.agentic_blue_eval import run_eval

MODELS = ["granite4.1:8b-ctx8k", "gpt-oss:20b", "huihui_ai/qwen3.5-abliterated:9b"]
SCENARIOS = ["kerberoast_to_da", "asrep_to_lateral", "meta3_ftp_backdoor"]
ARMS = ["raw", "tools", "harness"]

OUT_PATH = Path("/tmp/agentic_blue_sweep.json")

# Lock for thread-safe writes to the results file
_write_lock = Lock()


def _get_trials() -> int:
    """Get trial count from env, default 3."""
    return int(os.environ.get("TRIALS", "3"))


def _get_workers() -> int:
    """Get parallel worker count from env, default 4."""
    return int(os.environ.get("SWEEP_WORKERS", "4"))


def _run_cell(scenario: str, model: str, arms: list[str], trials: int) -> dict:
    """Run a single cell (scenario × model) with all its trials.

    Each trial runs the eval with the specified arms. Trials are serial
    within a cell (dependent — same model/scenario).

    Returns the aggregated result record for this cell.
    """
    t0 = time.monotonic()
    trial_results = []
    for _trial_i in range(trials):
        result = run_eval(scenario, model=model, arms=arms)
        trial_results.append(result)

    aggregated = _aggregate_trials(trial_results)
    wall_s = round(time.monotonic() - t0, 1)

    return {
        "scenario": scenario,
        "model": model,
        "_trials": trials,
        "_wall_s": wall_s,
        "ground_truth": trial_results[0].get("ground_truth", []) if trial_results else [],
        "arms": aggregated,
    }


def _checkpoint_result(record: dict, results: list[dict]) -> None:
    """Write a single cell result to the checkpoint file (thread-safe).

    Updates the in-memory results list AND writes to disk so interrupted
    runs keep what finished.
    """
    with _write_lock:
        # Remove any previous result for this (scenario, model) with fewer trials
        key = (record.get("scenario"), record.get("model"))
        existing = [
            r
            for r in results
            if (r.get("scenario"), r.get("model")) == key
            and r.get("_trials", 1) >= record.get("_trials", 1)
        ]
        if not existing:
            results[:] = [r for r in results if (r.get("scenario"), r.get("model")) != key]
            results.append(record)
            OUT_PATH.write_text(json.dumps(results, indent=2))


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

    Returns {model: {tier: {raw, tools, harness, delta_raw, delta_tools,
    raw_vals, harness_vals, tools_vals}}} where *_vals are per-scenario
    recall lists (for bootstrap CI).
    """
    # Group results by model
    by_model: dict[str, list[dict]] = {}
    for r in results:
        model = r.get("model", "")
        by_model.setdefault(model, []).append(r)

    deltas: dict[str, dict] = {}
    for model, model_results in by_model.items():
        # Collect per-scenario mean_recall for each arm+tier
        arm_tier_vals: dict[str, dict[str, list[float]]] = {}
        for r in model_results:
            for arm_name, arm_data in r.get("arms", {}).items():
                ts = arm_data.get("tiered_summary", {})
                arm_tier_vals.setdefault(arm_name, {})
                for tier in ["exact", "parent", "tactic"]:
                    arm_tier_vals[arm_name].setdefault(tier, [])
                    arm_tier_vals[arm_name][tier].append(ts.get(tier, {}).get("mean_recall", 0.0))

        # Compute averages
        model_tiers: dict[str, dict] = {}
        for tier in ["exact", "parent", "tactic"]:
            raw_vals = arm_tier_vals.get("raw", {}).get(tier, [0.0])
            tools_vals = arm_tier_vals.get("tools", {}).get(tier, [0.0])
            harness_vals = arm_tier_vals.get("harness", {}).get(tier, [0.0])

            raw_mr = sum(raw_vals) / len(raw_vals) if raw_vals else 0.0
            tools_mr = sum(tools_vals) / len(tools_vals) if tools_vals else 0.0
            harness_mr = sum(harness_vals) / len(harness_vals) if harness_vals else 0.0

            # Compute paired deltas for bootstrap CI
            paired_deltas = [h - r for h, r in zip(harness_vals, raw_vals, strict=False)]

            model_tiers[tier] = {
                "raw": round(raw_mr, 3),
                "tools": round(tools_mr, 3),
                "harness": round(harness_mr, 3),
                "delta_raw": round(harness_mr - raw_mr, 3),
                "delta_tools": round(harness_mr - tools_mr, 3),
                "raw_vals": raw_vals,
                "harness_vals": harness_vals,
                "tools_vals": tools_vals,
                "paired_deltas": paired_deltas,
            }

        deltas[model] = model_tiers

    return deltas


def _bootstrap_ci(
    paired_deltas: list[float], confidence: float = 0.95, n_boot: int = 10000
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for the mean of paired deltas.

    Args:
        paired_deltas: list of (harness_recall - raw_recall) per scenario
        confidence: CI level (default 0.95 = 95%)
        n_boot: number of bootstrap resamples

    Returns:
        (lower, upper) bounds of the CI.
    """
    import random

    if len(paired_deltas) < 2:
        mean = sum(paired_deltas) / len(paired_deltas) if paired_deltas else 0.0
        return (round(mean, 4), round(mean, 4))

    n = len(paired_deltas)
    boot_means: list[float] = []
    for _ in range(n_boot):
        sample = random.choices(paired_deltas, k=n)
        boot_means.append(sum(sample) / len(sample))

    boot_means.sort()
    alpha = 1.0 - confidence
    lower_idx = int(n_boot * (alpha / 2))
    upper_idx = int(n_boot * (1.0 - alpha / 2))
    lower_idx = max(0, min(lower_idx, n_boot - 1))
    upper_idx = max(0, min(upper_idx, n_boot - 1))

    return (round(boot_means[lower_idx], 4), round(boot_means[upper_idx], 4))


def _verdict_from_ci(ci_lower: float, ci_upper: float) -> str:
    """Determine verdict from confidence interval of harness−raw delta.

    - CI entirely above 0 → SIGNIFICANT-WIN
    - CI entirely below 0 → SIGNIFICANT-REGRESSION
    - CI crosses 0 → INCONCLUSIVE
    """
    if ci_lower > 0:
        return "SIGNIFICANT-WIN"
    if ci_upper < 0:
        return "SIGNIFICANT-REGRESSION"
    return "INCONCLUSIVE"


def _write_back_winning_config(results: list[dict]) -> str | None:
    """M5: Write arm-vs-arm delta report with confidence intervals as a cited wiki unit.

    Reports per-model harness−raw / harness−tools deltas per tier with 95% bootstrap CI.
    Labels each delta: SIGNIFICANT-WIN / SIGNIFICANT-REGRESSION / INCONCLUSIVE.
    Proposes seat config ONLY from the harness arm (production config).

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

    # Track verdicts
    verdicts: dict[str, dict[str, dict]] = {}

    body_lines = [
        "# Agentic Blue Eval — Arm-vs-Arm Delta Report (with Confidence Intervals)",
        "",
        f"**Trials per cell:** {n_trials}  ",
        f"**Scenarios:** {len(scenarios)}  ",
        f"**Sweep date:** {sweep_date}",
        "",
        "## Per-Model Arm Deltas with 95% Bootstrap CI",
        "",
        "The three-arm design exists to answer: **does the harness beat raw, for the same model, "
        "and by how much?** Each delta is reported with a 95% bootstrap confidence interval. "
        "A delta is only a WIN if its CI excludes 0 on the positive side; a REGRESSION only if "
        "the CI excludes 0 on the negative side; otherwise it is INCONCLUSIVE (within noise).",
        "",
    ]

    for model, model_tiers in sorted(deltas.items()):
        body_lines.append(f"### `{model}`")
        body_lines.append("")
        body_lines.append("| Tier | raw | harness | delta | 95% CI | verdict |")
        body_lines.append("|------|-----|---------|-------|--------|---------|")

        verdicts[model] = {}
        for tier in ["exact", "parent", "tactic"]:
            t = model_tiers[tier]
            paired = t.get("paired_deltas", [])
            ci_lo, ci_hi = _bootstrap_ci(paired)
            verdict = _verdict_from_ci(ci_lo, ci_hi)
            verdicts[model][tier] = {
                "delta": t["delta_raw"],
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "verdict": verdict,
            }

            dr = t["delta_raw"]
            delta_s = f"+{dr:.3f}" if dr >= 0 else f"{dr:.3f}"
            ci_s = f"[{ci_lo:+.3f}, {ci_hi:+.3f}]"

            body_lines.append(
                f"| {tier} | {t['raw']:.3f} | {t['harness']:.3f} | {delta_s} | {ci_s} | {verdict} |"
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

    # Verdict summary
    body_lines.extend(
        [
            "## Verdict Summary",
            "",
        ]
    )

    any_win = False
    any_regression = False
    for model, model_verdicts in sorted(verdicts.items()):
        for tier, v in sorted(model_verdicts.items()):
            if v["verdict"] == "SIGNIFICANT-WIN":
                any_win = True
                body_lines.append(
                    f"- **{model}/{tier}: SIGNIFICANT-WIN** — "
                    f"delta={v['delta']:+.3f}, CI=[{v['ci_lower']:+.3f}, {v['ci_upper']:+.3f}]"
                )
            elif v["verdict"] == "SIGNIFICANT-REGRESSION":
                any_regression = True
                body_lines.append(
                    f"- **{model}/{tier}: SIGNIFICANT-REGRESSION** — "
                    f"delta={v['delta']:+.3f}, CI=[{v['ci_lower']:+.3f}, {v['ci_upper']:+.3f}]"
                )

    if not any_win and not any_regression:
        body_lines.append(
            "- All deltas are INCONCLUSIVE — harness effect within noise at current power."
        )

    inconclusive_count = sum(
        1 for mv in verdicts.values() for v in mv.values() if v["verdict"] == "INCONCLUSIVE"
    )
    body_lines.append("")
    body_lines.append(
        f"**Inconclusive cells:** {inconclusive_count} — these cannot be declared wins or regressions."
    )
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

        body_lines.append(f"| Tier | harness recall | pass@{n_trials} | verdict |")
        body_lines.append("|------|---------------|---------|---------|")
        for tier in ["exact", "parent", "tactic"]:
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
            v = verdicts.get(best_harness_model, {}).get(tier, {}).get("verdict", "?")
            body_lines.append(
                f"| {tier} | {avg_recall:.3f} | {total_pass}/{total_possible} | {v} |"
            )
        body_lines.append("")

    body = "\n".join(body_lines)

    # Print delta summary to stdout
    print("\n" + "=" * 100)
    print("ARM-VS-ARM DELTAS WITH 95% BOOTSTRAP CI (harness contribution)")
    print("=" * 100)
    for model, model_tiers in sorted(deltas.items()):
        print(f"\n{model}:")
        print(
            f"  {'Tier':8s} | {'raw':>6s} | {'harness':>7s} | {'delta':>7s} | {'95% CI':>18s} | {'verdict':>20s}"
        )
        print(f"  {'-' * 8}-+-{'-' * 6}-+-{'-' * 7}-+-{'-' * 7}-+-{'-' * 18}-+-{'-' * 20}")
        for tier in ["exact", "parent", "tactic"]:
            v = verdicts[model][tier]
            ci_s = f"[{v['ci_lower']:+.4f}, {v['ci_upper']:+.4f}]"
            print(
                f"  {tier:8s} | {model_tiers[tier]['raw']:>6.3f} | "
                f"{model_tiers[tier]['harness']:>7.3f} | "
                f"{v['delta']:>+7.3f} | {ci_s:>18s} | {v['verdict']:>20s}"
            )

    if best_harness_model:
        print(f"\nRecommended seat: {best_harness_model} (harness arm)")

    # Write wiki unit
    try:
        from portal.platform.wiki.writeback import propose_unit

        unit_id = f"SEC_BENCH-agentic-blue-deltas-{time.strftime('%Y%m%d', time.gmtime())}"
        tags = ["agentic-blue", "maturation", "arm-deltas", "confidence-interval"]
        for model in deltas:
            tags.append(model.replace(":", "-"))

        proposed = propose_unit(
            {
                "id": unit_id,
                "title": f"Agentic Blue Arm Deltas (with CI): harness contribution ({sweep_date})",
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
    workers = _get_workers()

    # Parse CLI flags
    args = sys.argv[1:]
    all_captured = "--all-captured" in args
    arms = list(ARMS)  # default: all 3 arms

    # Allow env overrides for scenarios and models
    scenarios = SCENARIOS
    if os.environ.get("SWEEP_SCENARIOS"):
        scenarios = [s.strip() for s in os.environ["SWEEP_SCENARIOS"].split(",")]
    models = MODELS
    if os.environ.get("SWEEP_MODELS"):
        models = [m.strip() for m in os.environ["SWEEP_MODELS"].split(",")]

    # Parse --scenarios flag
    for arg in args:
        if arg.startswith("--scenarios="):
            scenarios = [s.strip() for s in arg.split("=", 1)[1].split(",")]

    # Parse --arms flag (iteration mode)
    for arg in args:
        if arg.startswith("--arms="):
            arms = [a.strip() for a in arg.split("=", 1)[1].split(",")]

    # Diagnostic flags
    diag_raw_full = "--diag-raw-full-haystack" in args
    diag_trace = "--diag-trace" in args
    if diag_raw_full:
        os.environ["DIAG_RAW_FULL_HAYSTACK"] = "true"
        print("DIAG: raw arm will use FULL haystack (not truncated to 12k)")
    if diag_trace:
        os.environ["DIAG_TRACE"] = "true"
        print("DIAG: harness/tools arms will log query trace")

    # --sample=N: random representative subset for iteration runs
    sample_n = None
    for arg in args:
        if arg.startswith("--sample="):
            sample_n = int(arg.split("=", 1)[1])

    # --step-cap=N: limit tool loop iterations (default 5, can reduce to 3)
    step_cap = None
    for arg in args:
        if arg.startswith("--step-cap="):
            step_cap = int(arg.split("=", 1)[1])
            os.environ["SWEEP_STEP_CAP"] = str(step_cap)
            print(f"STEP CAP: tool loop limited to {step_cap} iterations")

    # --all-captured: discover scenarios with local captures
    if all_captured:
        try:
            from portal.modules.security.core.exec_chain import SCENARIOS as ALL_SCENARIOS
            from portal.modules.security.core.siem.capture_store import list_captures

            available = [s for s in ALL_SCENARIOS if list_captures(s)]
            if available:
                scenarios = available
                print(f"--all-captured: found {len(scenarios)} scenarios with captures")
            else:
                print("--all-captured: no captures found, using defaults")
        except Exception as exc:
            print(f"--all-captured: failed to discover captures ({exc}), using defaults")

    # --sample=N: random representative subset for fast iteration
    if sample_n and sample_n < len(scenarios):
        import random

        random.seed(42)  # deterministic for reproducibility
        scenarios = sorted(random.sample(scenarios, sample_n))
        print(f"--sample={sample_n}: selected {len(scenarios)} scenarios for iteration")

    print(f"Sweep config: {len(scenarios)} scenarios x {len(models)} models x {trials} trials")
    print(f"Workers: {workers} (SWEEP_WORKERS={os.environ.get('SWEEP_WORKERS', '4')})")
    print(f"Arms: {arms}")
    print(f"Scenarios: {scenarios[:5]}{'...' if len(scenarios) > 5 else ''}")
    print(f"Models: {models}")
    print(f"Output: {OUT_PATH}")
    print()

    # Load existing results (supports incremental runs + checkpointing)
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

    # Build work queue: (scenario, model) cells that need running.
    # Model outer / scenario inner — with SWEEP_WORKERS=1 this means every
    # model loads once and runs all its scenarios before the next model
    # loads, instead of swapping models on nearly every cell (scenario-outer
    # order forces up to len(scenarios) x len(models) model loads instead of
    # len(models)). Cell contents and results are unaffected by ordering.
    work_queue = []
    for model in models:
        for scenario in scenarios:
            if (scenario, model) not in completed:
                work_queue.append((scenario, model))

    total_cells = len(scenarios) * len(models)
    skipped = total_cells - len(work_queue)
    if skipped:
        print(f"Skipping {skipped} already-completed cells")
    print(f"Running {len(work_queue)} cells with {workers} workers...")
    print()

    if not work_queue:
        print("All cells already completed. Nothing to do.")
    else:
        # Parallel execution via ThreadPoolExecutor
        t_sweep_start = time.monotonic()
        completed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all cells
            future_to_key = {}
            for scenario, model in work_queue:
                future = executor.submit(_run_cell, scenario, model, arms, trials)
                future_to_key[future] = (scenario, model)

            # Collect results as they complete
            for future in as_completed(future_to_key):
                scenario, model = future_to_key[future]
                completed_count += 1
                try:
                    record = future.result()
                    _checkpoint_result(record, results)

                    # Print summary for this cell
                    wall_s = record.get("_wall_s", 0)
                    aggregated = record.get("arms", {})
                    print(
                        f"[{completed_count}/{len(work_queue)}] DONE {scenario} x {model} in {wall_s}s",
                        flush=True,
                    )
                    for arm_name, arm_data in aggregated.items():
                        ts = arm_data.get("tiered_summary", {})
                        exact_mr = ts.get("exact", {}).get("mean_recall", 0)
                        parent_mr = ts.get("parent", {}).get("mean_recall", 0)
                        tactic_mr = ts.get("tactic", {}).get("mean_recall", 0)
                        exact_cls = ts.get("exact", {}).get("classification", "?")
                        parent_cls = ts.get("parent", {}).get("classification", "?")
                        tactic_cls = ts.get("tactic", {}).get("classification", "?")
                        print(
                            f"  {arm_name}: exact={exact_mr:.3f}({exact_cls}) "
                            f"parent={parent_mr:.3f}({parent_cls}) "
                            f"tactic={tactic_mr:.3f}({tactic_cls})"
                        )
                except Exception as exc:
                    print(
                        f"[{completed_count}/{len(work_queue)}] FAILED {scenario} x {model}: {exc}",
                        flush=True,
                    )

        sweep_wall = round(time.monotonic() - t_sweep_start, 1)
        print(f"\nParallel sweep completed in {sweep_wall}s ({sweep_wall / 60:.1f}min)")

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
