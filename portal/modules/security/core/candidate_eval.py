"""Candidate model evaluation mode — single-slot & solo, delta vs incumbent, isolated.

Reuses existing machinery (run_candidate_intake + step_models slot-pinning +
_CHAIN_ROLES) to bench ONE new model without a full-fleet run. Results write to
an isolated results/candidates/ path so the self-index baseline is never
polluted. PROMOTE_POLICY=confirm: reports deltas, never swaps fleet config.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ._data import RESULTS_DIR
from .exec_chain import (
    SCENARIOS,
    _prepare_scenario,
    _run_multimodel_chain,
)
from .intake import TPS_FLOOR, run_candidate_intake

# ── Fixed candidate-eval scenario set ────────────────────────────────────────
# A curated representative set spanning disciplines so every candidate faces the
# identical gauntlet and deltas are comparable across candidates and vs incumbent.
# NOT the full 70 (too slow, redundant for comparison); NOT pick-per-run (breaks
# comparability). --scenario override still allowed for a deep-dive.
CANDIDATE_EVAL_SCENARIOS: list[str] = [
    "kerberoast_to_da",  # AD — Kerberoast → lateral → exfil
    "web_sqli_dump",  # web injection — sqlmap via execute_bash
    "web_deserial_rce",  # web RCE — deserialization via execute_bash
    "meta3_full_chain",  # linux/host — full Metasploitable3 chain
    "web_ssrf",  # SSRF/OOB — cloud metadata via execute_bash
    "ctf_multi_service",  # multi-service — web + binary overflow
]

# ── Slot → _STEP_GROUPS mapping ──────────────────────────────────────────────
# Maps the --slot CLI arg to the _STEP_GROUPS keys that pin incumbents.
_SLOT_TO_GROUPS: dict[str, list[str]] = {
    "recon": ["planning"],
    "exploit": ["exploit"],
    "post": ["persist", "move", "exfil", "cleanup"],
}

# ── Slot → portal.yaml workspace (incumbent resolution) ──────────────────────
# Maps each slot to the workspace whose model_hint is the current fleet incumbent
# for that slot.  Reads live from portal.yaml — not hardcoded model names.
_SLOT_TO_WORKSPACE: dict[str, str] = {
    "recon": "auto-security",
    "exploit": "auto-pentest",
    "post": "auto-purpleteam-exec",
}

_PORTAL_YAML = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / "config" / "portal.yaml"
)

# ── Candidate results directory (isolated from baseline) ─────────────────────
CANDIDATES_DIR = RESULTS_DIR / "candidates"


def _get_incumbent_model(slot: str) -> str:
    """Resolve the real incumbent model for a slot from portal.yaml.

    Reads the model_hint from the workspace mapped by _SLOT_TO_WORKSPACE.
    Returns "" if the slot has no mapping, the YAML can't be read, or the
    workspace/model_hint is missing.
    """
    workspace = _SLOT_TO_WORKSPACE.get(slot)
    if not workspace:
        return ""
    try:
        data = yaml.safe_load(_PORTAL_YAML.read_text()) or {}
    except Exception:
        return ""
    workspaces = data.get("workspaces", {})
    ws_cfg = workspaces.get(workspace, {})
    return ws_cfg.get("model_hint", "")


def _build_step_models(slot: str, candidate: str, incumbent: str) -> dict[str, str]:
    """Build step_models dict for single-slot or solo mode.

    single-slot: pins incumbents for all groups except the candidate's slot.
    solo: candidate runs every slot.
    """
    if slot == "solo":
        return {"default": candidate}

    step_models: dict[str, str] = {"default": incumbent}
    for group in _SLOT_TO_GROUPS.get(slot, []):
        step_models[group] = candidate
    return step_models


def _compute_delta(candidate_results: list[dict], incumbent_results: list[dict]) -> list[dict]:
    """Compute per-scenario and aggregate deltas (candidate - incumbent).

    Returns a list of delta dicts, one per scenario + one aggregate.
    """
    deltas: list[dict] = []

    # Index incumbent results by scenario
    inc_by_sc: dict[str, dict] = {}
    for r in incumbent_results:
        sc = r.get("scenario", "")
        inc_by_sc[sc] = r

    # Per-scenario deltas
    for cr in candidate_results:
        sc = cr.get("scenario", "")
        ir = inc_by_sc.get(sc, {})
        delta = {
            "scenario": sc,
            "candidate_model": cr.get("model", ""),
            "incumbent_model": ir.get("model", ""),
            "unique_coverage_delta": round(
                cr.get("unique_coverage", 0) - ir.get("unique_coverage", 0), 3
            ),
            "order_accuracy_delta": round(
                cr.get("order_accuracy", 0) - ir.get("order_accuracy", 0), 3
            ),
            "chain_depth_delta": cr.get("chain_depth", 0) - ir.get("chain_depth", 0),
            "lab_success_delta": int(cr.get("lab_success", False))
            - int(ir.get("lab_success", False)),
            "elapsed_s_delta": round(cr.get("elapsed_s", 0) - ir.get("elapsed_s", 0), 1),
            "candidate_effort_tier": cr.get("effort_tier", "unknown"),
            "incumbent_effort_tier": ir.get("effort_tier", "unknown"),
        }
        deltas.append(delta)

    # Aggregate delta
    if candidate_results and incumbent_results:
        n = len(candidate_results)
        agg = {
            "scenario": "__aggregate__",
            "candidate_model": candidate_results[0].get("model", ""),
            "incumbent_model": incumbent_results[0].get("model", ""),
            "unique_coverage_delta": round(sum(d["unique_coverage_delta"] for d in deltas) / n, 3),
            "order_accuracy_delta": round(sum(d["order_accuracy_delta"] for d in deltas) / n, 3),
            "chain_depth_delta": round(sum(d["chain_depth_delta"] for d in deltas) / n, 1),
            "lab_success_delta": sum(d["lab_success_delta"] for d in deltas),
            "elapsed_s_delta": round(sum(d["elapsed_s_delta"] for d in deltas) / n, 1),
        }
        deltas.append(agg)

    return deltas


def _print_verdict(deltas: list[dict], slot: str) -> None:
    """Print a one-line verdict respecting confirm-policy."""
    agg = [d for d in deltas if d.get("scenario") == "__aggregate__"]
    if not agg:
        print("\n  VERDICT: no aggregate data (insufficient results)")
        return
    a = agg[0]
    uc = a["unique_coverage_delta"]
    ls = a["lab_success_delta"]
    sign_uc = "+" if uc >= 0 else ""
    sign_ls = "+" if ls >= 0 else ""
    direction = "BETTER" if (uc > 0 or ls > 0) else ("WORSE" if (uc < 0 or ls < 0) else "NEUTRAL")
    slot_label = slot.upper()
    print(
        f"\n  VERDICT [{slot_label}]: candidate {sign_uc}{uc:.3f} unique_coverage, "
        f"{sign_ls}{ls} lab_success vs incumbent — {direction} — "
        f"REVIEW for promotion (not auto-applied)"
    )


def candidate_eval_main(argv: list[str] | None = None) -> int:
    """Entry point for `python3 -m bench_security candidate-eval`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Candidate model eval — single-slot or solo, delta vs incumbent, isolated",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        metavar="MODEL",
        help="Candidate model ID to evaluate",
    )
    parser.add_argument(
        "--slot",
        required=True,
        choices=["recon", "exploit", "post", "solo"],
        help="Chain slot to test (solo = all slots)",
    )
    parser.add_argument(
        "--incumbent",
        default="",
        metavar="MODEL",
        help="Incumbent model override (auto-resolved from fleet config if omitted)",
    )
    parser.add_argument(
        "--scenario",
        default="",
        metavar="NAME",
        help="Single scenario override (default = CANDIDATE_EVAL_SCENARIOS)",
    )
    parser.add_argument(
        "--skip-pull",
        action="store_true",
        help="Skip Ollama model pull (reuse existing local model)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run: no inference, no lab dispatch",
    )
    parser.add_argument(
        "--lab-exec",
        action="store_true",
        help="Use real lab dispatch (default = synthetic)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Skip the intake TPS floor (still requires a successful pull + tool-call "
            "check). The TPS floor exists to protect chain responsiveness across the "
            "general fleet, but it disqualifies slower models before they're ever "
            "scored on capability — for a deliberate quality-over-speed evaluation "
            "(a 27B/35B model may out-detect a faster small model even at half the "
            "floor's t/s), pass --force to see the real delta instead of an intake "
            "rejection."
        ),
    )
    args = parser.parse_args(argv)

    candidate = args.candidate
    slot = args.slot

    # ── Resolve incumbent: explicit override → auto from config ──────────────
    incumbent = args.incumbent
    if not incumbent and slot != "solo":
        incumbent = _get_incumbent_model(slot)
    if not incumbent and slot != "solo":
        workspace = _SLOT_TO_WORKSPACE.get(slot, "?")
        print(
            f"  ERROR: could not resolve incumbent for slot '{slot}' "
            f"(workspace '{workspace}' not found or model_hint missing in portal.yaml).\n"
            f"  Pass --incumbent <model> explicitly, or fix the fleet config."
        )
        return 1
    if slot == "solo":
        incumbent = incumbent or "(solo — no incumbent pin)"

    # ── Step 1: Intake gate ──────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  CANDIDATE EVAL: {candidate}")
    print(f"  Slot: {slot} | Incumbent: {incumbent}")
    print(f"  Scenarios: {args.scenario or f'{len(CANDIDATE_EVAL_SCENARIOS)} fixed'}")
    print(f"{'=' * 60}\n")

    if not args.dry_run:
        gate_label = (
            "pull → tool-call (TPS floor forced off)" if args.force else "pull → TPS → tool-call"
        )
        print(f"  [1/4] Intake gate ({gate_label}) ...")
        intake = run_candidate_intake(
            [candidate],
            dry_run=False,
            skip_pull=args.skip_pull,
            tps_floor=0.0 if args.force else TPS_FLOOR,
        )
        if not intake or not intake[0].get("queued"):
            reason = intake[0].get("skip_reason", "unknown") if intake else "no result"
            print(f"  INTAKE FAILED: {reason}")
            print("  Candidate does not meet intake gates — not scoring.")
            return 1
        if args.force and intake[0].get("tps", 0) < TPS_FLOOR:
            print(
                f"  INTAKE PASSED (forced): TPS={intake[0].get('tps', 0):.1f} "
                f"below the {TPS_FLOOR:.0f} t/s floor — scoring anyway, chain turns "
                f"will run slower than the fleet norm."
            )
        else:
            print(f"  INTAKE PASSED: TPS={intake[0].get('tps', 0):.1f}, tool-call OK")
    else:
        print("  [1/4] Intake gate — DRY-RUN (skipped)")

    # ── Step 2: Build step_models ────────────────────────────────────────────
    print(f"\n  [2/4] Building step_models for slot={slot} ...")
    step_models = _build_step_models(slot, candidate, incumbent)
    print(f"  step_models: {step_models}")

    # ── Step 3: Run scenarios ────────────────────────────────────────────────
    from .exec_chain import CHAIN_TOOLS_BASE, BenchConfig

    cfg = BenchConfig(chain_tools=list(CHAIN_TOOLS_BASE))

    scenario_names = [args.scenario] if args.scenario else CANDIDATE_EVAL_SCENARIOS
    scenarios = []
    for name in scenario_names:
        if name not in SCENARIOS:
            print(f"  WARNING: scenario '{name}' not found — skipping")
            continue
        scenarios.append(SCENARIOS[name])

    if not scenarios:
        print("  ERROR: no valid scenarios to run")
        return 1

    print(f"\n  [3/4] Running {len(scenarios)} scenario(s) ...")

    # Run candidate
    candidate_results: list[dict] = []
    for sc in scenarios:
        gate = _prepare_scenario(sc, cfg, dry_run=args.dry_run, lab_exec=args.lab_exec)
        if not gate.get("ready"):
            print(f"  SKIP {sc['name']}: {gate.get('reason', 'target-unrecoverable')}")
            candidate_results.append(
                {
                    "scenario": sc["name"],
                    "outcome": "indeterminate",
                    "gate_reason": gate.get("reason"),
                }
            )
            continue
        print(f"\n  ── {sc['name']} (candidate) ──")
        if slot == "solo":
            # Solo: candidate runs all slots via _run_multimodel_chain
            result = _run_multimodel_chain(
                step_models={"default": candidate},
                default_model=candidate,
                cfg=cfg,
                dry_run=args.dry_run,
                lab_exec=args.lab_exec,
            )
            result["scenario"] = sc["name"]
            candidate_results.append(result)
        else:
            # Single-slot: multi-model with pinned incumbents
            result = _run_multimodel_chain(
                step_models=step_models,
                default_model=incumbent,
                cfg=cfg,
                dry_run=args.dry_run,
                lab_exec=args.lab_exec,
            )
            result["scenario"] = sc["name"]
            candidate_results.append(result)

    # Run incumbent baseline (skip if dry-run or same model)
    incumbent_results: list[dict] = []
    if not args.dry_run and incumbent:
        print(f"\n  [3b/4] Running incumbent baseline ({incumbent}) ...")
        for sc in scenarios:
            gate = _prepare_scenario(sc, cfg, dry_run=False, lab_exec=args.lab_exec)
            if not gate.get("ready"):
                print(f"  SKIP {sc['name']}: {gate.get('reason')}")
                continue
            print(f"\n  ── {sc['name']} (incumbent) ──")
            result = _run_multimodel_chain(
                step_models={"default": incumbent},
                default_model=incumbent,
                cfg=cfg,
                dry_run=False,
                lab_exec=args.lab_exec,
            )
            result["scenario"] = sc["name"]
            incumbent_results.append(result)

    # ── Step 4: Delta + output ───────────────────────────────────────────────
    print("\n  [4/4] Computing deltas ...")

    deltas = _compute_delta(candidate_results, incumbent_results)

    # Print absolute candidate scores
    print(f"\n{'=' * 60}")
    print("  CANDIDATE ABSOLUTE SCORES")
    print(f"{'=' * 60}")
    print(
        f"  {'Scenario':<30} {'Coverage':>8} {'Accuracy':>8} {'Depth':>6} {'Lab':>4} {'Tier':<18}"
    )
    print(f"  {'-' * 30} {'-' * 8} {'-' * 8} {'-' * 6} {'-' * 4} {'-' * 18}")
    for r in candidate_results:
        print(
            f"  {r.get('scenario', '?'):<30}"
            f"  {r.get('unique_coverage', 0):>7.2f}"
            f"  {r.get('order_accuracy', 0):>7.2f}"
            f"  {r.get('chain_depth', 0):>5}/{r.get('max_depth', 0)}"
            f"  {'Y' if r.get('lab_success') else 'N':>3}"
            f"  {r.get('effort_tier', '?'):<18}"
        )

    # Print deltas
    if incumbent_results:
        print(f"\n{'=' * 60}")
        print("  DELTA vs INCUMBENT")
        print(f"{'=' * 60}")
        print(f"  {'Scenario':<30} {'Cov Δ':>7} {'Acc Δ':>7} {'Depth Δ':>7} {'Lab Δ':>6}")
        print(f"  {'-' * 30} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 6}")
        for d in deltas:
            if d.get("scenario") == "__aggregate__":
                continue
            print(
                f"  {d['scenario']:<30}"
                f"  {d['unique_coverage_delta']:>+6.3f}"
                f"  {d['order_accuracy_delta']:>+6.3f}"
                f"  {d['chain_depth_delta']:>+6d}"
                f"  {d['lab_success_delta']:>+5d}"
            )
        # Aggregate
        agg = [d for d in deltas if d.get("scenario") == "__aggregate__"]
        if agg:
            a = agg[0]
            print(f"  {'─' * 30} {'─' * 7} {'─' * 7} {'─' * 7} {'─' * 6}")
            print(
                f"  {'AGGREGATE':<30}"
                f"  {a['unique_coverage_delta']:>+6.3f}"
                f"  {a['order_accuracy_delta']:>+6.3f}"
                f"  {a['chain_depth_delta']:>+6.0f}"
                f"  {a['lab_success_delta']:>+5d}"
            )

    _print_verdict(deltas, slot)

    # ── Write isolated results ───────────────────────────────────────────────
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    # candidate IDs are frequently hf.co/<org>/<repo>[:quant] — ':' alone isn't
    # enough, the embedded '/' makes write_text() below try to create a
    # subdirectory that doesn't exist and silently lose the result (confirmed
    # live 2026-07-03: RedTeamLab-redteam-v5's candidate-eval printed its full
    # verdict table to stdout but never wrote a results file).
    safe_candidate = candidate.replace(":", "_").replace("/", "_")
    out_path = CANDIDATES_DIR / f"cand_{safe_candidate}_{slot}_{ts}.json"

    output = {
        "mode": "candidate-eval",
        "candidate": candidate,
        "incumbent": incumbent,
        "slot": slot,
        "scenarios": scenario_names,
        "timestamp": ts,
        "candidate_results": candidate_results,
        "incumbent_results": incumbent_results,
        "deltas": deltas,
    }
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results written → {out_path}")
    print("  (Isolated from baseline — self-index unaffected)")

    return 0
