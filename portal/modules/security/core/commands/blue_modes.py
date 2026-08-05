"""Blue-mode / rescore CLI handlers extracted from cli.py main() — C3 Tier A."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .._data import RESULTS_DIR
from ..cli import _parse_barrier_tools_arg, _parse_budgets_arg
from ..scoring import (
    score_argument_adaptation,
    score_chain_coherence,
    score_pivot_correctness,
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
