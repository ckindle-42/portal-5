"""``python3 -m portal.modules.security.core goal ...`` — the evidence surface
for TASK_SEC_GOAL_DECIDE_V1 (Stage 2 Phase 4).

Deliberately no --lab-exec here: Stage 2 has no live path. The absence is
the safety property.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DOCS_DIR = Path(__file__).resolve().parents[4] / "docs"


def goal_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="portal security goal",
        description="Goal-driven engagement planning — proposal + dry-run only (Stage 2)",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_plan = sub.add_parser("plan", help="Propose a dry-run plan for a goal")
    p_plan.add_argument(
        "--intent", required=True, help="Free-text intent, e.g. 'poke this machine'"
    )
    p_plan.add_argument("--role", required=True, choices=["red", "blue", "purple"])
    p_plan.add_argument("--target", action="append", default=[], dest="targets")
    p_plan.add_argument("--scope-net", default=None, help="Scope target (net or host)")
    p_plan.add_argument("--budget-iters", type=int, default=10)
    p_plan.add_argument("--budget-wall-sec", type=int, default=1800)
    p_plan.add_argument("--budget-lab-actions", type=int, default=30)
    p_plan.add_argument("--domain-hint", default=None)
    p_plan.add_argument("--workspace", default=None)
    p_plan.add_argument(
        "--logs", default=None, help="For blue goals: seed log path (informational)"
    )
    p_plan.add_argument("--json", action="store_true")

    p_eval = sub.add_parser("eval", help="Run the proposal-quality harness over seeded targets")
    p_eval.add_argument("--workspace", default=None)
    p_eval.add_argument("--role", default="red", choices=["red", "blue", "purple"])
    p_eval.add_argument("--json", action="store_true")

    p_replay = sub.add_parser("replay", help="Re-render a saved plan report")
    p_replay.add_argument("plan_path", help="Path to a saved plan JSON")

    args = parser.parse_args(argv)

    if args.subcommand == "plan":
        return _cmd_plan(args)
    if args.subcommand == "eval":
        return _cmd_eval(args)
    if args.subcommand == "replay":
        return _cmd_replay(args)
    return 1


def _cmd_plan(args) -> int:
    from .goal import EngagementGoal
    from .loop import run_goal_engagement

    targets = args.targets or ([args.scope_net] if args.scope_net else [])
    scope_targets = [args.scope_net] if args.scope_net else list(targets)
    goal = EngagementGoal(
        intent=args.intent,
        role=args.role,
        targets=targets,
        scope={"targets": scope_targets},
        budget={
            "max_iterations": args.budget_iters,
            "max_wall_clock_sec": args.budget_wall_sec,
            "max_lab_actions": args.budget_lab_actions,
        },
        domain_hint=args.domain_hint,
    )
    report = run_goal_engagement(goal, dry_run=True, workspace=args.workspace)

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    target_tag = (targets[0] if targets else "notarget").replace("/", "_").replace(".", "-")
    out_path = DOCS_DIR / f"GOAL_PLAN_{target_tag}_{ts}.md"
    try:
        out_path.write_text(_render_plan_markdown(goal, report))
    except OSError:
        out_path = None

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_render_plan_markdown(goal, report))
    if out_path:
        print(f"\nPlan report written: {out_path}")
    return 0 if report.get("status") != "rejected" else 1


def _render_plan_markdown(goal, report: dict) -> str:
    lines = [
        f"# Goal Plan — {goal.intent}",
        "",
        f"- role: {goal.role}",
        f"- targets: {goal.targets}",
        f"- status: {report.get('status')}",
        f"- stop_reason: {report.get('stop_reason')}",
        f"- iterations: {report.get('iterations')}",
        f"- escalations: {report.get('escalations')}",
        "",
        "## Proposed actions",
        "",
    ]
    for i, step in enumerate(report.get("plan", []), 1):
        lines.append(
            f"{i}. **{step.get('action')}** (tool: `{step.get('tool')}`, "
            f"confidence: {step.get('confidence'):.2f})\n"
            f"   - reason: {step.get('reason')}\n"
            f"   - expected_oracle: {step.get('expected_oracle')}\n"
            f"   - alternatives_considered: {step.get('alternatives_considered')}"
        )
    if not report.get("plan"):
        lines.append("(no actions proposed)")
    return "\n".join(lines)


def _cmd_eval(args) -> int:
    from .goal_eval import eval_proposals

    result = eval_proposals(workspace=args.workspace, role=args.role)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        agg = result["aggregate"]
        print(f"Targets evaluated: {agg['targets_evaluated']}")
        print(f"Relevance rate:    {agg['relevance_rate']:.1%}")
        print(f"Grounding rate:    {agg['grounding_rate']:.1%}")
        print(f"Non-flailing rate: {agg['non_flailing_rate']:.1%}")
        print(f"Coverage rate:     {agg['coverage_rate']:.1%}")
        print()
        for p in result["per_target"]:
            tag = "OK" if p["coverage"] else "  "
            print(f"  [{tag}] {p['target']:<32} -> {p['proposed_action']}")
    return 0


def _cmd_replay(args) -> int:
    path = Path(args.plan_path)
    if not path.exists():
        print(f"ERROR: plan file not found: {path}")
        return 1
    data = json.loads(path.read_text())
    print(f"Goal: {data.get('goal_intent')} (role={data.get('goal_role')})")
    print(f"Stop reason: {data.get('stop_reason')}  iterations={data.get('iterations')}")
    for i, step in enumerate(data.get("plan", []), 1):
        print(f"  {i}. {step.get('action')} -> {step.get('tool')} ({step.get('reason')})")
    return 0
