"""Blue-mode / rescore CLI handlers extracted from cli.py main() — C3 Tier A."""

from __future__ import annotations

import contextlib
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .._data import _LAB_EXEC_AVAILABLE, RESULTS_DIR
from ..chain import (
    _WEB_SEARCH_CHAIN_TOOL,
    SCENARIOS,
    TPS_FLOOR,
    _prepare_scenario,
    _run_multimodel_chain,
    run_chain_tests,
)
from ..chain import run_candidate_intake as _run_candidate_intake_chain
from ..cli import _parse_barrier_tools_arg, _parse_budgets_arg
from ..lab import (
    print_lab_probe_report,
    probe_lab_services,
    snapshot_lab_vms,
    verify_lab_targets_reachable,
)
from ..scoring import (
    score_argument_adaptation,
    score_chain_coherence,
    score_pivot_correctness,
)
from .context import BenchRun
from .run import _print_intake_summary


def _write_checkpoint(run: BenchRun) -> None:
    """Persist progress so far to .partial.json after each scenario (C3 Tier C-1).

    Scenario sweeps bypass the workspace-benchmark checkpoint path, so they
    need this independent checkpoint. Best-effort writes must never crash
    the run they are protecting.
    """
    if not run.checkpoint_path:
        return
    with contextlib.suppress(Exception):
        run.checkpoint_path.write_text(
            json.dumps(
                {
                    "timestamp": run.ts,
                    "in_progress": True,
                    "chain_tests": run.chain_results,
                    "blue_tests": run.blue_results,
                    "purple_tests": run.purple_results,
                },
                indent=2,
                default=str,
            )
        )


def run_blue_mode_orchestrated(args) -> None:
    # ── Standalone: --blue-mode orchestrated ─────────────────────────────────
    # BUILD_PROGRAM_SEC_BLUE_ORCHESTRATION_V2 Slice 7. Not a --purple prompt
    # variant (I5: no auto-security prod routing touched) — runs the
    # tool/reasoning/expert discovery pipeline directly against a captured
    # episode and exits. Additive-only; every other --blue-mode value is
    # unaffected.
    from portal.platform.inference.config import load_portal_config

    from ..agentic_blue_eval import load_episode, score_findings_tiered
    from ..blue_orchestrate import SectionSpec, run_blue_orchestration

    if not args.replay_captured_red:
        print("  ERROR: --blue-mode orchestrated requires --replay-captured-red")
        return

    episode = load_episode(args.scenario)
    if episode is None:
        print(f"  ERROR: no captured episode found for scenario '{args.scenario}'")
        return

    default_variant = (
        load_portal_config()
        .workspaces.get("auto-security")
        .variants.get("blueteam-orchestrated", {})
    )
    tool_model = args.tool_model or default_variant.get("tool_model")
    reasoning_model = args.reasoning_model or default_variant.get("reasoning_model")
    expert_model = args.expert_model or default_variant.get("expert_model")
    if not (tool_model and reasoning_model and expert_model):
        print(
            "  ERROR: --tool-model/--reasoning-model/--expert-model not set and "
            "no default found in config/portal.yaml's blueteam-orchestrated variant"
        )
        return

    budgets = _parse_budgets_arg(args.budgets)
    barrier_roles = _parse_barrier_tools_arg(args.barrier_tools)

    print(f"Blue orchestration — scenario={episode.scenario} target={episode.target_host}")
    print(f"  tool_model={tool_model}")
    print(f"  reasoning_model={reasoning_model}")
    print(f"  expert_model={expert_model}")
    if args.mentor_model:
        print(f"  mentor_model={args.mentor_model}")
    if budgets:
        print(f"  budgets={budgets}")
    if barrier_roles:
        print(f"  barrier_tools={sorted(barrier_roles)}")

    sections = [
        SectionSpec(role="tool", model=tool_model, needs_tools=True),
        SectionSpec(
            role="reasoning",
            model=reasoning_model,
            use_barrier_tools="reasoning" in barrier_roles,
        ),
        SectionSpec(role="expert", model=expert_model, use_barrier_tools="expert" in barrier_roles),
    ]
    if args.mentor_model:
        sections.append(SectionSpec(role="mentor", model=args.mentor_model))
    result = run_blue_orchestration(
        episode,
        sections=sections,
        max_rounds=args.max_orchestration_rounds,
        budgets=budgets,
        dry_run=args.dry_run,
    )
    scoring = score_findings_tiered(set(result.technique_ids), set(episode.techniques))

    print(f"\n  Verdict       : {result.verdict}")
    print(f"  Technique IDs : {result.technique_ids}")
    print(f"  Match grade   : {result.match_grade}  similar_to={result.similar_to}")
    print(f"  Rounds/elapsed: {result.rounds} / {result.elapsed_s}s")
    print(f"  Overall recall: {scoring['overall']['recall']}")

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"sec_blue_orchestrated_{episode.scenario}_{ts}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "scenario": episode.scenario,
                "target_host": episode.target_host,
                "ground_truth": episode.techniques,
                "tool_model": tool_model,
                "reasoning_model": reasoning_model,
                "expert_model": expert_model,
                "verdict": result.verdict,
                "technique_ids": result.technique_ids,
                "evidence": result.evidence,
                "reasoning": result.reasoning,
                "match_grade": result.match_grade,
                "similar_to": result.similar_to,
                "rounds": result.rounds,
                "elapsed_s": result.elapsed_s,
                "trace": result.trace,
                "scoring": scoring,
            },
            indent=2,
            default=str,
        )
    )
    print(f"  Results written -> {out_path}")
    return


def run_blue_mode_orchestrated_2section(args) -> None:
    # ── Standalone: --blue-mode orchestrated-2section (Slice 8 ablation) ─────
    # design §6.1's "V1 shape" — tool + merged reasoning/expert, one model
    # hunts and concludes itself. Same standalone contract as 'orchestrated'
    # above (not a --purple prompt variant, no prod routing touched, I5).
    from ..agentic_blue_eval import load_episode, score_findings_tiered
    from ..blue_orchestrate import SectionSpec, run_blue_orchestration

    if not args.replay_captured_red:
        print("  ERROR: --blue-mode orchestrated-2section requires --replay-captured-red")
        return

    episode = load_episode(args.scenario)
    if episode is None:
        print(f"  ERROR: no captured episode found for scenario '{args.scenario}'")
        return

    tool_model = args.tool_model
    merged_model = args.merged_model
    if not (tool_model and merged_model):
        print("  ERROR: --tool-model and --merged-model are both required")
        return

    print(
        f"Blue orchestration (2-section) — scenario={episode.scenario} target={episode.target_host}"
    )
    print(f"  tool_model={tool_model}")
    print(f"  merged_model={merged_model}")

    sections = [
        SectionSpec(role="tool", model=tool_model, needs_tools=True),
        SectionSpec(role="merged", model=merged_model),
    ]
    result = run_blue_orchestration(
        episode,
        sections=sections,
        max_rounds=args.max_orchestration_rounds,
        dry_run=args.dry_run,
    )
    scoring = score_findings_tiered(set(result.technique_ids), set(episode.techniques))

    print(f"\n  Verdict       : {result.verdict}")
    print(f"  Technique IDs : {result.technique_ids}")
    print(f"  Match grade   : {result.match_grade}  similar_to={result.similar_to}")
    print(f"  Rounds/elapsed: {result.rounds} / {result.elapsed_s}s")
    print(f"  Overall recall: {scoring['overall']['recall']}")

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"sec_blue_orchestrated_2section_{episode.scenario}_{ts}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "scenario": episode.scenario,
                "target_host": episode.target_host,
                "ground_truth": episode.techniques,
                "tool_model": tool_model,
                "merged_model": merged_model,
                "verdict": result.verdict,
                "technique_ids": result.technique_ids,
                "evidence": result.evidence,
                "reasoning": result.reasoning,
                "match_grade": result.match_grade,
                "similar_to": result.similar_to,
                "rounds": result.rounds,
                "elapsed_s": result.elapsed_s,
                "trace": result.trace,
                "scoring": scoring,
            },
            indent=2,
            default=str,
        )
    )
    print(f"  Results written -> {out_path}")
    return


def run_blue_mode_council(args) -> None:
    # ── Standalone: --blue-mode council (GATE-D ablation Part II-A) ──────────
    # TASK-SEC-GATED-ABLATION-TO-COUNCIL-V1. Same standalone contract as
    # 'orchestrated'/'orchestrated-2section' above (not a --purple prompt
    # variant, no prod routing touched, I5 confirm-only) — gathers evidence
    # once via the roster's lead model, then has every --council-models
    # member independently conclude from that same evidence; a deterministic
    # quorum vote decides, with the fed --expert-model as an optional arbiter
    # for a no-quorum split.
    from portal.platform.inference.config import load_portal_config

    from ..agentic_blue_eval import load_episode, score_findings_tiered
    from ..blue_orchestrate import SectionSpec, run_blue_orchestration

    if not args.replay_captured_red:
        print("  ERROR: --blue-mode council requires --replay-captured-red")
        return

    episode = load_episode(args.scenario)
    if episode is None:
        print(f"  ERROR: no captured episode found for scenario '{args.scenario}'")
        return

    default_variant = (
        load_portal_config().workspaces.get("auto-security").variants.get("blueteam-council", {})
    )
    tool_model = args.tool_model or default_variant.get("tool_model")
    council_models_raw = args.council_models or default_variant.get("council_models")
    expert_model = args.expert_model or default_variant.get("expert_model")
    council_models = (
        [m.strip() for m in council_models_raw.split(",") if m.strip()]
        if isinstance(council_models_raw, str)
        else list(council_models_raw or [])
    )
    if not (tool_model and len(council_models) > 1):
        print(
            "  ERROR: --tool-model and --council-models (2+ comma-separated models) "
            "are required, and no default found in config/portal.yaml's "
            "blueteam-council variant"
        )
        return

    budgets = _parse_budgets_arg(args.budgets)
    barrier_roles = _parse_barrier_tools_arg(args.barrier_tools)

    print(
        f"Blue orchestration (council) — scenario={episode.scenario} target={episode.target_host}"
    )
    print(f"  tool_model={tool_model}")
    print(f"  council_models={council_models}")
    print(f"  expert_model (arbiter)={expert_model}")
    print(f"  quorum={args.quorum}")
    if args.mentor_model:
        print(f"  mentor_model={args.mentor_model}")
    if budgets:
        print(f"  budgets={budgets}")
    if barrier_roles:
        print(f"  barrier_tools={sorted(barrier_roles)}")

    sections = [SectionSpec(role="tool", model=tool_model, needs_tools=True)]
    sections += [
        SectionSpec(role="reasoning", model=m, use_barrier_tools="reasoning" in barrier_roles)
        for m in council_models
    ]
    if expert_model:
        sections.append(
            SectionSpec(
                role="expert", model=expert_model, use_barrier_tools="expert" in barrier_roles
            )
        )
    if args.mentor_model:
        sections.append(SectionSpec(role="mentor", model=args.mentor_model))
    result = run_blue_orchestration(
        episode,
        sections=sections,
        max_rounds=args.max_orchestration_rounds,
        budgets=budgets,
        dry_run=args.dry_run,
        quorum=args.quorum,
    )
    scoring = score_findings_tiered(set(result.technique_ids), set(episode.techniques))

    print(f"\n  Verdict       : {result.verdict}")
    print(f"  Technique IDs : {result.technique_ids}")
    print(f"  Match grade   : {result.match_grade}  similar_to={result.similar_to}")
    print(f"  Rounds/elapsed: {result.rounds} / {result.elapsed_s}s")
    print(f"  Overall recall: {scoring['overall']['recall']}")

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"sec_blue_council_{episode.scenario}_{ts}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "scenario": episode.scenario,
                "target_host": episode.target_host,
                "ground_truth": episode.techniques,
                "tool_model": tool_model,
                "council_models": council_models,
                "expert_model": expert_model,
                "quorum": args.quorum,
                "verdict": result.verdict,
                "technique_ids": result.technique_ids,
                "evidence": result.evidence,
                "reasoning": result.reasoning,
                "match_grade": result.match_grade,
                "similar_to": result.similar_to,
                "rounds": result.rounds,
                "elapsed_s": result.elapsed_s,
                "trace": result.trace,
                "scoring": scoring,
            },
            indent=2,
            default=str,
        )
    )
    print(f"  Results written -> {out_path}")
    return


def run_blue_mode_multichain(args) -> None:
    # ── Standalone: --blue-mode multichain (multi-model multi-chain analyst) ──
    # N FULLY INDEPENDENT investigative chains — each its own tool+reasoning+
    # expert hunt with its own hypothesis/evidence pulls — consolidated into an
    # AUTO_CONFIRM / ESCALATE / DISMISS operator decision. Same standalone
    # contract as the arms above (not a --purple variant, no prod routing, I5).
    # Unlike council (one shared evidence pool), each chain gathers its own.
    from portal.platform.inference.config import load_portal_config

    from ..agentic_blue_eval import load_episode
    from ..blue_orchestrate import run_multichain_orchestration

    if not args.replay_captured_red:
        print("  ERROR: --blue-mode multichain requires --replay-captured-red")
        return

    episode = load_episode(args.scenario)
    if episode is None:
        print(f"  ERROR: no captured episode found for scenario '{args.scenario}'")
        return

    default_variant = (
        load_portal_config().workspaces.get("auto-security").variants.get("blueteam-council", {})
    )
    tool_model = args.tool_model or default_variant.get("tool_model")
    chain_models_raw = args.chain_analyst_models or default_variant.get("council_models")
    chain_models = (
        [m.strip() for m in chain_models_raw.split(",") if m.strip()]
        if isinstance(chain_models_raw, str)
        else list(chain_models_raw or [])
    )
    # expert_model is OPTIONAL here — default None gives each chain its own
    # model end to end (fully independent). A shared expert is opt-in.
    expert_model = args.expert_model
    if not (tool_model and len(chain_models) > 1):
        print(
            "  ERROR: --tool-model and --chain-analyst-models (2+ comma-separated "
            "models) are required, and no default found in config/portal.yaml's "
            "blueteam-council variant"
        )
        return

    print(
        f"Blue orchestration (multichain) — scenario={episode.scenario} "
        f"target={episode.target_host}"
    )
    print(f"  tool_model={tool_model}")
    print(f"  chain_models (independent)={chain_models}")
    print(f"  expert_model (shared, optional)={expert_model}")
    print(f"  quorum={args.quorum}")

    result = run_multichain_orchestration(
        episode,
        tool_model=tool_model,
        chain_models=chain_models,
        expert_model=expert_model,
        quorum=args.quorum,
        max_rounds=args.max_orchestration_rounds,
        dry_run=args.dry_run,
    )
    from ..agentic_blue_eval import score_analyst_outcome

    consolidation = next((t for t in result.trace if t.get("section") == "consolidation"), {})
    # result.technique_ids = confirmed known-bad; result.similar_to = review
    # leads. Score both channels so a correct escalation is a win, not a
    # miss (dimension-1 fix): operational_recall = confirmed OR correctly
    # escalated to a human. Gate-demoted claims are passed separately so
    # they can never convert into escalation credit (2026-07-23).
    scoring = score_analyst_outcome(
        set(result.technique_ids),
        set(result.similar_to),
        set(episode.techniques),
        ungrounded_claims=set(result.ungrounded_claims),
    )

    print(f"\n  Decision      : {consolidation.get('decision')}")
    print(f"  Verdict       : {result.verdict}")
    print(f"  Confirmed     : {result.technique_ids}  (known-bad channel)")
    print(f"  Review leads  : {result.similar_to}  (escalation channel)")
    if result.ungrounded_claims:
        print(
            f"  Ungrounded    : {result.ungrounded_claims}  "
            "(gate-demoted claims — audit only, never credited)"
        )
    print(f"  Evidence div. : {consolidation.get('evidence_diversity')} distinct source(s)")
    if consolidation.get("escalation_reason"):
        print(f"  Escalation    : {consolidation.get('escalation_reason')}")
    print(f"  Rounds/elapsed: {result.rounds} / {result.elapsed_s}s")
    print(f"  Confirmed recall  : {scoring['confirmed']['overall']['recall']}")
    print(f"  Escalation recall : {scoring['escalation']['escalation_recall']}")
    print(
        f"  OPERATIONAL recall: {scoring['operational']['operational_recall']}  "
        "(caught OR correctly escalated)"
    )

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = (
        Path(args.output)
        if args.output
        else RESULTS_DIR / f"sec_blue_multichain_{episode.scenario}_{ts}.json"
    )
    out_path.write_text(
        json.dumps(
            {
                "scenario": episode.scenario,
                "target_host": episode.target_host,
                "ground_truth": episode.techniques,
                "tool_model": tool_model,
                "chain_models": chain_models,
                "expert_model": expert_model,
                "quorum": args.quorum,
                "decision": consolidation.get("decision"),
                "verdict": result.verdict,
                "confirmed_techniques": result.technique_ids,
                "review_leads": result.similar_to,
                "technique_ids": result.technique_ids,
                "evidence": result.evidence,
                "reasoning": result.reasoning,
                "match_grade": result.match_grade,
                "similar_to": result.similar_to,
                "ungrounded_claims": result.ungrounded_claims,
                "evidence_diversity": consolidation.get("evidence_diversity"),
                "escalation_reason": consolidation.get("escalation_reason"),
                "rounds": result.rounds,
                "elapsed_s": result.elapsed_s,
                "trace": result.trace,
                "scoring": scoring,
            },
            indent=2,
            default=str,
        )
    )
    print(f"  Results written -> {out_path}")
    return


def run_rescore(args) -> None:
    # ── Rescore mode: re-derive scores from saved data ────────────────────
    _rescore_file = Path(args.rescore)
    if not _rescore_file.exists():
        print(f"ERROR: rescore file not found: {_rescore_file}")
        return
    _rescore_path = (
        Path(args.output)
        if args.output
        else _rescore_file.with_stem(_rescore_file.stem + "_rescored")
    )
    _rescore_data = json.loads(_rescore_file.read_text())
    print(f"Rescoring: {_rescore_file}")
    print(f"  Original timestamp: {_rescore_data.get('timestamp', '?')}")

    _rescored_count = 0
    # Rescore chain tests
    for ct in _rescore_data.get("chain_tests", []):
        if ct.get("outcome") == "dry_run":
            continue
        tools_called = ct.get("tools_called", [])
        tools_called_args = [
            {"name": t.get("tool", ""), "args": t.get("arguments", {})} for t in tools_called
        ]
        observations = ct.get("lab_observations", {})
        # Re-derive scoring metrics
        adaptation = score_argument_adaptation(tools_called_args, observations)
        coherence = score_chain_coherence(tools_called_args, observations)
        pivot = score_pivot_correctness(tools_called_args)
        ct["argument_adaptation"] = adaptation
        ct["coherence"] = coherence
        ct["pivot_correctness"] = pivot
        _rescored_count += 1

    # Rescore exec chain results inside workspace results
    for r in _rescore_data.get("results", []):
        for ec in r.get("exec_chain", []):
            if ec.get("_blue_defender"):
                continue
            steps_hit = ec.get("steps_hit", [])
            steps_proven = ec.get("steps_proven", [])
            ec["success_rate"] = (
                round(len(steps_proven) / max(len(steps_hit), 1), 3) if steps_hit else 0.0
            )
            _rescored_count += 1

    _rescore_data["rescored"] = True
    _rescore_data["rescored_at"] = datetime.now(tz=UTC).isoformat()
    _rescore_data["rescored_count"] = _rescored_count
    _rescore_path.write_text(json.dumps(_rescore_data, indent=2))
    print(f"  Rescored {_rescored_count} entries")
    print(f"  Output: {_rescore_path}")
    return


def _collect_retry_failed(args, _retry_failed_prompts, _retry_failed_scenarios) -> dict | None:
    """Retry mode: find failures from previous run, re-run only those (C3 Tier B)."""
    if args.retry_failed:
        _retry_path = Path(args.retry_failed)
        if not _retry_path.exists():
            print(f"ERROR: retry file not found: {_retry_path}")
            return None
        _retry_data = json.loads(_retry_path.read_text())
        # Find failed chain tests (depth < max_depth, or stalled). chain_tests entries
        # from --chain-models --all-scenarios runs carry a "scenario" tag (not
        # "prompts_failed" — that field belongs to a different result shape and was
        # never actually populated here), so failures are tracked by scenario name and
        # used to restrict scenarios_to_run below — this is what makes --retry-failed
        # actually retry only the failed chain tests instead of silently retrying none.
        for ct in _retry_data.get("chain_tests", []):
            if ct.get("outcome") == "dry_run":
                continue
            depth = ct.get("chain_depth", 0)
            max_d = ct.get("max_depth", 1)
            if (depth < max_d or ct.get("stalled")) and ct.get("scenario"):
                _retry_failed_scenarios.add(ct["scenario"])
        # Find failed exec chain entries (success_rate < 0.5)
        for r in _retry_data.get("results", []):
            for ec in r.get("exec_chain", []):
                if ec.get("_blue_defender"):
                    continue
                sr = ec.get("success_rate", 1.0)
                if sr < 0.5:
                    _retry_failed_prompts.add(r.get("prompt_key", ""))
        _retry_failed_prompts.discard("")
        # Find failed purple tests — red never landed (target was down, dispatch
        # stub, etc.).  The E2E results store data in purple_tests, not
        # chain_tests, so --retry-failed must check here too or it silently
        # finds "no failures" and exits.  red_landed=False means no real
        # execution happened — the scenario needs a live re-run.  Scenarios
        # where red landed but blue_f1=0 are valid data (model capability
        # floor), not infrastructure failures.
        #
        # Exclude scenarios that were explicitly gated as target-unrecoverable
        # (no amount of retrying will help — the target doesn't exist) and
        # web_* placeholders that reference non-existent endpoints.
        _gated_scenarios: set[str] = set()
        for pt in _retry_data.get("purple_tests", []):
            if pt.get("gate_reason") == "target-unrecoverable":
                _gated_scenarios.add(pt.get("scenario", ""))
        for pt in _retry_data.get("purple_tests", []):
            name = pt.get("scenario", "")
            if not name:
                continue
            # Skip unrecoverable targets — retrying won't help
            if name in _gated_scenarios:
                continue
            # Skip web_* placeholders — no real vulnerable app deployed
            if name.startswith("web_"):
                continue
            if not pt.get("red_landed", False):
                _retry_failed_scenarios.add(name)
        return _retry_data
    return {}


def run_candidate_intake(args) -> bool:
    """Candidate intake: pull → TPS gate → audit-tools → queue (C3 Tier B)."""
    if args.candidate_intake:
        intake_results = _run_candidate_intake_chain(
            args.candidate_intake,
            dry_run=args.dry_run,
            skip_pull=getattr(args, "skip_pull", False),
            tps_floor=TPS_FLOOR,
        )
        _print_intake_summary(intake_results)
        if (
            not args.dry_run
            and not args.workspaces
            and not args.chain_models
            and not args.exec_chain_models
        ):
            return True  # intake-only run; nothing else to do
    return False


def run_any_chain(args, _any_chain, _enabled_prompts) -> str:
    """Shared lab setup: probe + snapshot (C3 Tier B)."""
    _snapshot_name = ""
    if _any_chain:
        if (args.lab_exec or args.lab_snapshot or args.probe_lab) and not _LAB_EXEC_AVAILABLE:
            print(
                "  WARNING: lab exec requested but bench_lab_exec.py not importable — using synthetic"
            )

        # ── Mandatory reachability gate (independent of --probe-lab) ────────────
        # Added 2026-06-30: --probe-lab only auto-filters prompts, and that filter is
        # bypassed by an explicit --prompt list and never consulted on the
        # --chain-models + --all-scenarios path. This gate runs unconditionally
        # whenever --lab-exec is set, on both paths, before any model inference.
        if args.lab_exec and _LAB_EXEC_AVAILABLE and not args.force_unreachable_lab:
            print("\n  [lab-gate] verifying DC/SRV reachability before chain dispatch ...")
            if not verify_lab_targets_reachable(dry_run=args.dry_run):
                print(
                    "\n  ABORTING: lab targets unreachable — this run would otherwise "
                    "produce lab_success=0 across the board with no signal anything was "
                    "wrong (see docs/LAB_REACHABILITY_DIAGNOSTIC_2026-06-30.md). Verify "
                    "VM state and network path, or pass --force-unreachable-lab to "
                    "override deliberately.\n"
                )
                sys.exit(1)

        # ── Lab service auto-discovery ────────────────────────────────────────
        if args.probe_lab and _LAB_EXEC_AVAILABLE:
            _probe = probe_lab_services(dry_run=args.dry_run)
            print_lab_probe_report(_probe)
            _svc_to_prompt: dict[str, list[str]] = {
                "smb": [
                    "kerberoasting",
                    "asrep_roasting",
                    "pass_the_hash",
                    "smb_enum_relay",
                    "bloodhound_ad_recon",
                    "rbcd_attack",
                    "ad_dcsync_golden_ticket",
                    "adcs_template_abuse",
                    "eternalblue_ms17010",
                    "htb_responder_chain",
                ],
                "meta3_smb": [
                    "kerberoasting",
                    "asrep_roasting",
                    "pass_the_hash",
                    "smb_enum_relay",
                    "bloodhound_ad_recon",
                    "eternalblue_ms17010",
                    "lateral_movement",
                    "htb_responder_chain",
                    "meta3_full_compromise",
                ],
                "meta3_mysql": ["sqli_manual", "mysql_udf_privesc", "meta3_full_compromise"],
                "meta3_http": [
                    "web_recon_basics",
                    "web_shell_upload",
                    "iis_webdav_scanner",
                    "meta3_full_compromise",
                ],
                "meta3_tomcat": ["tomcat_manager", "meta3_full_compromise"],
                "meta3_ftp": [
                    "web_recon_basics",
                    "ftp_backdoor",
                    "meta3_full_compromise",
                ],
                "redis": ["redis_to_rce"],
                "nfs": ["nfs_privesc_chain"],
                "http_8080": ["lfi_to_rce", "htb_lfi_log_poison"],
                "http_8081": ["tomcat_manager"],
                "http_8983": ["log4shell_rce"],
                "vulnapp_web": [
                    "sqli_manual",
                    "web_shell_upload",
                    "ssrf_exploitation",
                    "lfi_to_rce",
                    "web_recon_basics",
                    "htb_sqli_to_shell",
                ],
            }
            for svc, prompts in _svc_to_prompt.items():
                if _probe.get(svc):
                    _enabled_prompts.update(prompts)
            if _enabled_prompts:
                print(
                    f"  [probe-lab] auto-filter: {len(_enabled_prompts)} prompts with reachable services\n"
                )

        # ── Proxmox VM snapshot before chain ──────────────────────────────────
        if args.lab_snapshot and _LAB_EXEC_AVAILABLE:
            _snapshot_name = f"bench-{int(time.monotonic())}"
            if not args.dry_run:
                snapshot_lab_vms(_snapshot_name, dry_run=args.dry_run)
            print(f"  [proxmox] snapshot '{_snapshot_name}' created\n")
    return _snapshot_name


def run_retry_data(args, _retry_data, chain_results, results, ts, output_data) -> dict:
    """Merge mode: replace only the entries this retry re-ran (C3 Tier B)."""
    if _retry_data:
        # Merge mode: start from the previous run, replace only the entries this
        # retry actually re-ran (matched by (scenario, model) for chain_tests, by
        # prompt_key for results), and keep everything else from the original file
        # untouched — a chain-only retry must not silently drop old blue/purple/
        # matrix_results data it never re-ran.
        def _ct_key(ct: dict) -> tuple:
            return (ct.get("scenario"), ct.get("model"))

        retried_ct_keys = {_ct_key(r) for r in chain_results}
        merged_chain_tests = [
            ct for ct in _retry_data.get("chain_tests", []) if _ct_key(ct) not in retried_ct_keys
        ]
        merged_chain_tests.extend(chain_results)

        retried_prompt_keys = {r.get("prompt_key") for r in results if r.get("prompt_key")}
        merged_results = [
            r
            for r in _retry_data.get("results", [])
            if r.get("prompt_key") not in retried_prompt_keys
        ]
        merged_results.extend(results)

        merged = dict(_retry_data)
        merged["timestamp"] = ts
        merged["chain_tests"] = merged_chain_tests
        merged["results"] = merged_results
        output_data = merged
        print(
            f"  Retry: merged {len(retried_ct_keys)} chain_test(s) + "
            f"{len(retried_prompt_keys)} result(s) into "
            f"{len(merged_chain_tests)} total chain_tests, {len(merged_results)} total results"
        )
    return output_data


def run_chain_models(run: BenchRun) -> None:
    # Step 2: tool call chain test (red), aligned to the selected scenario(s)
    if run.args.dynamic_cve:
        run.cfg.dynamic_cve_mode = True
        if _WEB_SEARCH_CHAIN_TOOL not in run.cfg.chain_tools:
            run.cfg.chain_tools.append(_WEB_SEARCH_CHAIN_TOOL)
        print("  [dynamic-cve] web_search offered; nmap banners only, CVE must be researched")

    if run.args.judgment:
        run.cfg.judgment_mode = True
        print(
            f"  [judgment] scope_discipline on — decoy {run.cfg.scope_decoy_host} injected into nmap; "
            f"per-step timeout {run.cfg.step_timeout_s:.0f}s; refusal scenario runs after chain tests"
        )

    # A retry-scenario target implies scanning the full scenario set to find it —
    # the single default `scenario` almost never matches, which previously made
    # --retry-scenarios silently select zero scenarios unless --all-scenarios was
    # ALSO passed by hand (found live 2026-07-02: a targeted retry ran to completion
    # having dispatched nothing, because this defaulted to [scenario] instead).
    scenarios_to_run = (
        list(SCENARIOS.values())
        if (run.args.all_scenarios or run._retry_failed_scenarios)
        else [run.scenario]
    )
    if run._retry_failed_scenarios:
        scenarios_to_run = [
            sc for sc in scenarios_to_run if sc["name"] in run._retry_failed_scenarios
        ]
        print(
            f"  Retry: restricting to {len(scenarios_to_run)} failed scenario(s): "
            f"{sorted(s['name'] for s in scenarios_to_run)}"
        )
    all_scenario_results: dict[str, list[dict]] = {}

    for sc in scenarios_to_run:
        print(f"\n── Scenario: {sc['name']} ──")
        # Phase 3: target readiness gate — verify→heal→re-verify
        gate = _prepare_scenario(sc, run.cfg, dry_run=run.args.dry_run, lab_exec=run.args.lab_exec)
        if not gate.get("ready"):
            # Unrecoverable target → indeterminate, NEVER lab_success=False
            print(f"  SKIP: {gate.get('reason', 'target-unrecoverable')}")
            indeterminate_result = {
                "model": ",".join(run.args.chain_models) if run.args.chain_models else "unknown",
                "scenario": sc["name"],
                "chain_depth": 0,
                "outcome": "indeterminate",
                "gate_reason": gate.get("reason", "target-unrecoverable"),
                "lab_success": False,
                "lab_observations": {"open_ports": []},
            }
            run.chain_results.append(indeterminate_result)
            all_scenario_results.setdefault(sc["name"], []).append(indeterminate_result)
            _write_checkpoint(run)
            continue
        if gate.get("healed"):
            print(f"  Target healed: {gate.get('reason')} → {gate.get('host')}:{gate.get('port')}")
        scenario_start = time.time()
        # Episode-scoped packet capture at the DinD attack boundary --
        # found live 2026-07-24: this red-only --all-scenarios path never
        # called start_network_capture/stop_network_capture at all (only
        # blue.py's separate --purple orchestration did), so every
        # red-only run fell back entirely to the old lossy post-hoc
        # scrape (collect_and_ship_scenario_telemetry's docker/access-log
        # read after the fact) -- the exact Hop 2/3 evidence-chain gap
        # 993b6a97 built network_capture.py to fix, just never wired into
        # this code path. Without it, a captured red run has no lossless
        # sensor-observed evidence for blue to ever detect, regardless of
        # whether the attack itself succeeded -- 52/68 full-depth
        # completions in the first run through this gap showed zero
        # ground-truth coverage.
        from .episode import new_episode_id

        episode_id = new_episode_id(sc["name"])
        network_capture = None
        if run.args.lab_exec and not run.args.dry_run:
            from portal.modules.security.core.siem.network_capture import (
                start_network_capture,
            )

            network_capture = start_network_capture(episode_id, sc.get("target_host"))
        try:
            sc_results = run_chain_tests(
                run.args.chain_models, run.cfg, dry_run=run.args.dry_run, lab_exec=run.args.lab_exec
            )
        finally:
            if network_capture is not None:
                from portal.modules.security.core.siem.network_capture import (
                    stop_network_capture,
                )

                network_capture = stop_network_capture(network_capture)
        for r in sc_results:
            r["scenario"] = sc["name"]
            r["episode_id"] = episode_id
        all_scenario_results[sc["name"]] = sc_results
        run.chain_results.extend(sc_results)
        _write_checkpoint(run)

        if run.args.lab_exec and not run.args.dry_run:
            # Get red's raw host telemetry into the SIEM up front, at its true
            # attack time — this is the whole point of re-running Step 1: a
            # captured red run should be independently verifiable in Splunk,
            # not just present as a local JSON summary. Non-AD/DC/meta3
            # targets only (WinEventBackend queries the DC live, no shipping
            # needed there); best-effort, never blocks red's own results.
            from portal.modules.security.core.blue import collect_and_ship_scenario_telemetry
            from portal.modules.security.core.siem.capture_store import save_evidence

            cap_path, indexed, tele_err = None, None, ""
            try:
                cap_path, indexed, tele_err = collect_and_ship_scenario_telemetry(
                    sc,
                    scenario_start,
                    lab_exec=run.args.lab_exec,
                    dry_run=run.args.dry_run,
                    episode_id=episode_id,
                    network_telemetry=network_capture.telemetry if network_capture else None,
                    pcap_path=network_capture.local_pcap_path if network_capture else None,
                )
            except Exception as _cap_exc:
                logging.warning("capture failed for %s: %s", sc["name"], _cap_exc)
            with contextlib.suppress(Exception):
                for r in sc_results:
                    save_evidence(
                        "red",
                        sc["name"],
                        {
                            "model": r.get("model"),
                            "telemetry_capture_path": cap_path,
                            "telemetry_indexed_confirmed": indexed,
                            "telemetry_collection_error": tele_err,
                            **r,
                        },
                    )

        # Tear down ephemeral vulhub targets once their scenario is done —
        # cmd_up/heal never stops them, so a full --all-scenarios run leaves
        # every healed CVE container running for the rest of the run, and the
        # vulhub LXC's memory climbs monotonically until later heals start
        # timing out (found live 2026-07-03: 25/70 scenarios lost to this on a
        # single run). Best-effort: a failed teardown just means the next
        # scenario's `cmd_up` finds the container already there.
        if sc.get("vulhub_env") and run.args.lab_exec and not run.args.dry_run:
            from scripts.lab_targets import cmd_down

            cmd_down(sc["vulhub_env"], dry_run=run.args.dry_run)

        # Pace back-to-back scenarios — teardown/heal/exploitation lands right
        # on top of each other otherwise, and repeated full/retry runs have
        # crashed real lab infra under it (meta3 crashing mid-run, the vulhub
        # LXC's docker daemon thrashing under concurrent network teardown +
        # new-container-create). A short settle window between scenarios costs
        # little against a ~30-45min run and lets Docker/Proxmox actually
        # finish releasing a target's resources before the next one claims them.
        if run.args.lab_exec and not run.args.dry_run:
            time.sleep(5)

        # Multi-model chain for this scenario (if --step-models provided)
        if run._step_models and run.args.chain_models:
            print(f"\n── Multi-model chain: {sc['name']} ──")
            mm_result = _run_multimodel_chain(
                step_models=run._step_models,
                default_model=run.args.chain_models[0],
                cfg=run.cfg,
                dry_run=run.args.dry_run,
                lab_exec=run.args.lab_exec,
            )
            run.multimodel_results.append({**mm_result, "scenario": sc["name"]})

    # Compute per-model averages across scenarios when --all-scenarios
    if run.args.all_scenarios and not run.args.dry_run:
        by_model: dict[str, list[dict]] = {}
        for _sc_name, sc_res in all_scenario_results.items():
            for r in sc_res:
                by_model.setdefault(r["model"], []).append(r)
        for model, runs in by_model.items():
            avg_unique = sum(r.get("unique_coverage", 0) for r in runs) / len(runs)
            avg_acc = sum(r.get("order_accuracy", 0) for r in runs) / len(runs)
            avg_depth = sum(r.get("chain_depth", 0) for r in runs) / len(runs)
            avg_time = sum(r.get("elapsed_s", 0) for r in runs) / len(runs)
            run.scenario_averages.append(
                {
                    "model": model,
                    "scenarios_run": [
                        r.get("scenario", sc)
                        for r, sc in zip(runs, [s["name"] for s in scenarios_to_run], strict=False)
                    ],
                    "avg_unique_coverage": round(avg_unique, 3),
                    "avg_order_accuracy": round(avg_acc, 3),
                    "avg_chain_depth": round(avg_depth, 1),
                    "avg_elapsed_s": round(avg_time, 1),
                }
            )
        run.scenario_averages.sort(
            key=lambda x: (x["avg_unique_coverage"], x["avg_order_accuracy"]), reverse=True
        )
        if run.scenario_averages:
            print("\n── Scenario Averages (all scenarios) ──")
            print(f"{'Model':<48} {'Unique':>7} {'Acc':>5} {'Depth':>6} {'Time':>6}")
            print("-" * 80)
            for avg in run.scenario_averages:
                print(
                    f"{avg['model'][:48]:<48}"
                    f"  {avg['avg_unique_coverage']:>6.2f}"
                    f"  {avg['avg_order_accuracy']:>4.2f}"
                    f"  {avg['avg_chain_depth']:>5.1f}"
                    f"  {avg['avg_elapsed_s']:>4.0f}s"
                )
