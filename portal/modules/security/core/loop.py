"""Autonomous engagement loop — self-continuing security controller.

Wires existing organs into a perceive→decide→act→verify→learn cycle:
- Perceive: accumulate_observations from lab output
- Decide: playbooks.resolve_phases against current observations
- Act: drive the multi-model chain runner via lab_dispatch
- Verify: named oracles (N/N reproduction)
- Learn: field-journal recall + write-back

Bounded by playbook scope, budget, stop conditions, and hard caps in code.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import field_journal as journal
from . import oracles as oracle_mod
from .playbooks import load_playbook, resolve_phases, validate_playbook

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_DIR = RESULTS_DIR / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

# ── Hard caps (defensive floor — playbook budget can only be stricter) ────────

HARD_MAX_ITERATIONS = 50
HARD_MAX_WALL_CLOCK_SEC = 7200
HARD_MAX_LAB_ACTIONS = 200


@dataclass
class EngagementState:
    engagement_id: str
    playbook_name: str
    observations: dict = field(default_factory=dict)
    completed_phases: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    iterations: int = 0
    lab_actions: int = 0
    started_at: float = 0.0
    escalations: list[str] = field(default_factory=list)
    capsules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "playbook_name": self.playbook_name,
            "observations": self.observations,
            "completed_phases": self.completed_phases,
            "findings": self.findings,
            "iterations": self.iterations,
            "lab_actions": self.lab_actions,
            "started_at": self.started_at,
            "escalations": self.escalations,
            "capsules": self.capsules,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EngagementState:
        return cls(
            engagement_id=d.get("engagement_id", ""),
            playbook_name=d.get("playbook_name", ""),
            observations=d.get("observations", {}),
            completed_phases=d.get("completed_phases", []),
            findings=d.get("findings", []),
            iterations=d.get("iterations", 0),
            lab_actions=d.get("lab_actions", 0),
            started_at=d.get("started_at", 0.0),
            escalations=d.get("escalations", []),
            capsules=d.get("capsules", []),
        )


# ── Scope guard ──────────────────────────────────────────────────────────────


def enforce_scope(action_target: str, pb_scope: dict) -> bool:
    """Return True if action_target is within the playbook's declared scope."""
    targets = pb_scope.get("targets", []) if pb_scope else []
    if not targets:
        return True  # no scope declared → allow (playbook validation should catch this)
    return any(t in action_target for t in targets)


# ── Budget + stop + escalate checks ──────────────────────────────────────────


def _check_budget(state: EngagementState, pb: dict) -> str | None:
    """Return stop reason if budget exceeded, else None."""
    budget = pb.get("budget", {})
    wall_elapsed = time.monotonic() - state.started_at

    if state.iterations >= min(
        budget.get("max_iterations", HARD_MAX_ITERATIONS),
        HARD_MAX_ITERATIONS,
    ):
        return (
            "hard_cap"
            if budget.get("max_iterations", 0) <= HARD_MAX_ITERATIONS
            else "budget_exhausted"
        )

    if wall_elapsed >= min(
        budget.get("max_wall_clock_sec", HARD_MAX_WALL_CLOCK_SEC),
        HARD_MAX_WALL_CLOCK_SEC,
    ):
        return "hard_cap" if wall_elapsed >= HARD_MAX_WALL_CLOCK_SEC else "budget_exhausted"

    if state.lab_actions >= min(
        budget.get("max_lab_actions", HARD_MAX_LAB_ACTIONS),
        HARD_MAX_LAB_ACTIONS,
    ):
        return "hard_cap" if state.lab_actions >= HARD_MAX_LAB_ACTIONS else "budget_exhausted"

    return None


def _check_stop(pb: dict, observations: dict) -> bool:
    """Return True if any stop_condition is met."""
    for cond in pb.get("stop_conditions", []):
        field = cond.get("field", "")
        expected = cond.get("equals")
        if field in observations and observations[field] == expected:
            return True
    return False


def _check_escalate(state: EngagementState, pb: dict) -> str | None:
    """Return escalation reason if any escalation trigger fires, else None."""
    escalate = pb.get("escalate_when", [])
    for trigger in escalate:
        if isinstance(trigger, str):
            if trigger == "out_of_scope_action" and any(
                e.startswith("out_of_scope_action") for e in state.escalations
            ):
                return "out_of_scope_action"
        elif isinstance(trigger, dict):
            if "repeated_failure" in trigger:
                threshold = trigger["repeated_failure"]
                if _count_recent_failures(state) >= threshold:
                    return f"repeated_failure (>= {threshold})"
            if "oracle_rejection_rate_gt" in trigger:
                threshold = trigger["oracle_rejection_rate_gt"]
                if _oracle_rejection_rate(state) > threshold:
                    return f"oracle_rejection_rate_gt ({threshold})"
    return None


def _count_recent_failures(state: EngagementState) -> int:
    """Count failed verification attempts in findings."""
    return sum(1 for f in state.findings if not f.get("verified", False))


def _oracle_rejection_rate(state: EngagementState) -> float:
    """Fraction of oracle checks that were rejected."""
    total = sum(f.get("oracle_attempts", 0) for f in state.findings)
    if total == 0:
        return 0.0
    rejected = sum(
        f.get("oracle_attempts", 0) - f.get("oracle_successes", 0) for f in state.findings
    )
    return rejected / total


# ── Main loop ────────────────────────────────────────────────────────────────


def run_engagement(
    playbook_path: str,
    *,
    dry_run: bool = False,
    lab_exec: bool = False,
    workspace: str | None = None,
    auto_continue_safe: bool = False,
    notify_on_success: bool = False,
) -> dict:
    """Run a playbook to a stop condition. Returns an engagement report."""
    pb = load_playbook(playbook_path)
    problems = validate_playbook(pb)
    if problems:
        return {
            "status": "rejected",
            "reason": f"playbook validation failed: {', '.join(problems)}",
            "findings": [],
            "stop_reason": "invalid_playbook",
        }

    eng_id = f"{pb.get('name', 'engagement')}-{int(time.monotonic())}"
    state = EngagementState(
        engagement_id=eng_id,
        playbook_name=pb.get("name", playbook_path),
        started_at=time.monotonic(),
    )

    # Recall prior journal entries
    try:
        prior = journal.recall(
            scenario_category=pb.get("name", ""),
            keywords=[pb.get("name", "")],
            limit=3,
        )
    except Exception:
        prior = []

    if dry_run:
        return _dry_run_report(pb, state, prior)

    return _run_loop(pb, state, prior, lab_exec, workspace, auto_continue_safe, notify_on_success)


# ── Notifications (TASK_SEC_LOOP_NOTIFY_V1) ────────────────────────────────────
# Reuses the EXISTING notification subsystem (portal.platform.inference.notifications)
# rather than building a new one — the loop just fires AlertEvents through the
# shared dispatcher. Non-fatal by construction: a notify failure must never
# abort or fail the engagement.

_shared_dispatcher = None  # built once per process


def _loop_notify_enabled() -> bool:
    return os.environ.get("LOOP_NOTIFY_ENABLED", "true").lower() in ("true", "1", "yes")


def _get_shared_dispatcher():
    global _shared_dispatcher
    if _shared_dispatcher is not None:
        return _shared_dispatcher

    from portal.platform.inference.notifications import NotificationDispatcher
    from portal.platform.inference.notifications.channels import (
        EmailChannel,
        PushoverChannel,
        SlackChannel,
        TelegramChannel,
        WebhookChannel,
    )

    disp = NotificationDispatcher()
    # add_channel() is itself a no-op when NOTIFICATIONS_ENABLED is false, so
    # this is safe to build unconditionally.
    disp.add_channel(SlackChannel())
    disp.add_channel(TelegramChannel())
    disp.add_channel(EmailChannel())
    disp.add_channel(PushoverChannel())
    disp.add_channel(WebhookChannel())
    _shared_dispatcher = disp
    return disp


def _resume_cmd(engagement_id: str) -> str:
    return f"python3 -m portal.modules.security.core loop resume {engagement_id}"


def _notify(
    event_type_name: str,
    message: str,
    *,
    engagement_id: str,
    stop_reason: str | None = None,
    detail: str | None = None,
    resume_cmd: str | None = None,
) -> None:
    """Fire an AlertEvent through the shared NotificationDispatcher.
    Fire-and-forget, non-fatal — a notify failure is logged and swallowed,
    never propagated to the caller. A no-op when LOOP_NOTIFY_ENABLED is false
    (the global NOTIFICATIONS_ENABLED gate is enforced by the dispatcher/
    channels themselves — both must be on for anything to actually send)."""
    if not _loop_notify_enabled():
        return
    try:
        from portal.platform.inference.notifications import AlertEvent, EventType

        event_type = getattr(EventType, event_type_name)
        disp = _get_shared_dispatcher()
        disp._schedule(
            disp.dispatch(
                AlertEvent(
                    type=event_type,
                    message=message,
                    metadata={
                        "engagement_id": engagement_id,
                        "stop_reason": stop_reason,
                        "detail": detail,
                        "resume_cmd": resume_cmd,
                    },
                )
            )
        )
    except Exception as exc:
        logger.warning("loop notify failed (non-fatal): %s", exc)


def _run_loop(
    pb: dict,
    state: EngagementState,
    prior: list[dict],
    lab_exec: bool,
    workspace: str | None,
    auto_continue_safe: bool,
    notify_on_success: bool = False,
) -> dict:
    """Execute the engagement loop (real execution)."""
    while True:
        # Budget check
        budget_stop = _check_budget(state, pb)
        if budget_stop:
            _write_checkpoint(state, budget_stop)
            _notify(
                "ENGAGEMENT_STUCK",
                f"Engagement '{state.engagement_id}' hit {budget_stop} after "
                f"{state.iterations} iteration(s), {len(state.completed_phases)} phase(s) complete.",
                engagement_id=state.engagement_id,
                stop_reason=budget_stop,
                detail=f"last_phase={state.completed_phases[-1] if state.completed_phases else 'none'}",
                resume_cmd=_resume_cmd(state.engagement_id),
            )
            return _build_report(state, pb, prior, budget_stop)

        # Stop condition check
        if _check_stop(pb, state.observations):
            _write_checkpoint(state, "goal_met")
            if notify_on_success:
                _notify(
                    "ENGAGEMENT_COMPLETE",
                    f"Engagement '{state.engagement_id}' completed — goal met after "
                    f"{state.iterations} iteration(s).",
                    engagement_id=state.engagement_id,
                    stop_reason="goal_met",
                )
            return _build_report(state, pb, prior, "goal_met")

        # Escalation check
        escalation = _check_escalate(state, pb)
        if escalation and (escalation == "out_of_scope_action" or not auto_continue_safe):
            state.escalations.append(escalation)
            _write_checkpoint(state, f"escalated:{escalation}")
            _notify(
                "ENGAGEMENT_ESCALATED",
                f"Engagement '{state.engagement_id}' escalated: {escalation}. Needs an operator decision.",
                engagement_id=state.engagement_id,
                stop_reason=f"escalated:{escalation}",
                detail=escalation,
                resume_cmd=_resume_cmd(state.engagement_id),
            )
            return _build_report(state, pb, prior, f"escalated:{escalation}")

        # Resolve runnable phases
        ready = resolve_phases(pb, state.observations)
        if not ready:
            _write_checkpoint(state, "no_runnable_phase")
            _notify(
                "ENGAGEMENT_STUCK",
                f"Engagement '{state.engagement_id}' has no runnable phase — dead end "
                f"after {len(state.completed_phases)} phase(s) complete.",
                engagement_id=state.engagement_id,
                stop_reason="no_runnable_phase",
                resume_cmd=_resume_cmd(state.engagement_id),
            )
            return _build_report(state, pb, prior, "no_runnable_phase")

        # Execute the first ready phase (simplified — real version loops all ready phases)
        phase = ready[0]
        pid = phase.get("id", f"phase-{state.iterations}")

        if phase.get("manual"):
            state.escalations.append(f"manual_phase:{pid}")
            _write_checkpoint(state, f"escalated:manual_phase:{pid}")
            _notify(
                "ENGAGEMENT_ESCALATED",
                f"Engagement '{state.engagement_id}' needs a manual phase: {pid}.",
                engagement_id=state.engagement_id,
                stop_reason=f"escalated:manual_phase:{pid}",
                detail=pid,
                resume_cmd=_resume_cmd(state.engagement_id),
            )
            return _build_report(state, pb, prior, f"escalated:manual_phase:{pid}")

        # Execute phase steps
        for step in phase.get("steps", []):
            target = step.get("target", "")
            if target and not enforce_scope(target, pb.get("scope", {})):
                state.escalations.append(f"out_of_scope_action:{target}")
                state.lab_actions += 1
                continue

            if lab_exec:
                _execute_step_real(state, step, pb)
            state.lab_actions += 1

        state.completed_phases.append(pid)
        state.iterations += 1


def _execute_step_real(state: EngagementState, step: dict, pb: dict) -> None:
    """Execute a single step against the real lab (placeholder for multi-model runner)."""
    from .lab import lab_dispatch

    tool = step.get("tool", "")
    result = lab_dispatch(tool, step, dry_run=False)

    # Accumulate observations
    if isinstance(result, str) and "open" in result.lower():
        state.observations["open_ports"] = state.observations.get("open_ports", []) + [True]

    # Run oracle if declared
    oracle_id = step.get("oracle")
    if oracle_id:
        verdict = oracle_mod.verify_finding(
            finding={"oracle": oracle_id},
            lab_output=result,
            observations=state.observations,
        )
        state.findings.append(
            {
                "oracle": oracle_id,
                "verified": verdict.verified,
                "evidence": verdict.evidence[:500],
                "oracle_attempts": verdict.required,
                "oracle_successes": verdict.reproductions,
            }
        )


def _dry_run_report(pb: dict, state: EngagementState, prior: list[dict]) -> dict:
    """Build a dry-run engagement plan."""
    phases_plan = []
    for phase in pb.get("phases", []):
        phases_plan.append(
            {
                "id": phase.get("id", "?"),
                "manual": phase.get("manual", False),
                "depends_on": phase.get("depends_on", []),
                "steps": len(phase.get("steps", [])),
            }
        )

    return {
        "status": "dry_run",
        "playbook": pb.get("name", "?"),
        "scope": pb.get("scope"),
        "budget": pb.get("budget"),
        "stop_conditions": pb.get("stop_conditions"),
        "phases_plan": phases_plan,
        "prior_engagements": len(prior),
        "engagement_id": state.engagement_id,
    }


def _build_report(state: EngagementState, pb: dict, prior: list[dict], stop_reason: str) -> dict:
    """Build the final engagement report and write journal + capsules."""
    report = {
        "status": "completed",
        "engagement_id": state.engagement_id,
        "playbook": state.playbook_name,
        "stop_reason": stop_reason,
        "iterations": state.iterations,
        "lab_actions": state.lab_actions,
        "completed_phases": state.completed_phases,
        "findings": state.findings,
        "escalations": state.escalations,
        "capsules": state.capsules,
        "observations": state.observations,
        "prior_engagements_consulted": len(prior),
    }

    # Write journal entry
    with contextlib.suppress(Exception):
        journal.record_engagement(
            chain_result={
                "chain_depth": len(state.completed_phases),
                "tools_called": state.findings,
                "verified": any(f.get("verified") for f in state.findings),
                "compromise_confirmed": any(f.get("verified") for f in state.findings),
            },
            scenario={"category": pb.get("name", "loop"), "goal": stop_reason},
            engagement_id=state.engagement_id,
        )

    # Stamp
    try:
        from tests.benchmarks.capability_lib import stamp_result_meta

        report = stamp_result_meta(report)
    except ImportError:
        pass

    return report


# ── Checkpoint / Resume ──────────────────────────────────────────────────────


def _write_checkpoint(state: EngagementState, reason: str) -> Path:
    """Write EngagementState to a checkpoint file."""
    out = CHECKPOINT_DIR / f"{state.engagement_id}.json"
    data = state.to_dict()
    data["checkpoint_reason"] = reason
    data["checkpoint_at"] = time.time()
    try:
        from tests.benchmarks.capability_lib import stamp_result_meta

        data = stamp_result_meta(data)
    except ImportError:
        pass
    out.write_text(json.dumps(data, indent=2))
    return out


# ── Goal-driven open-ended mode (Stage 2 — proposal + dry-run only) ───────────


def run_goal_engagement(
    goal,
    *,
    dry_run: bool = True,
    workspace: str | None = None,
    max_steps: int | None = None,
) -> dict:
    """Open-ended loop: perceive -> capability.query -> decide_next_action ->
    (DRY-RUN: record proposed action, simulate its expected_observation_delta)
    -> repeat until a stop condition / budget / hard cap / escalation /
    no_applicable_capability.

    dry_run defaults True. Live actuation is not implemented in this task —
    a non-dry-run call raises NotImplementedError('live actuation is Stage 3').
    This keeps the Stage-2/Stage-3 boundary explicit in code, not just in docs.
    """
    from .goal import validate_goal
    from .goal_decide import decide_next_action

    problems = validate_goal(goal)
    if problems:
        return {
            "status": "rejected",
            "reason": f"goal validation failed: {', '.join(problems)}",
            "plan": [],
            "stop_reason": "invalid_goal",
        }

    if not dry_run:
        raise NotImplementedError("live actuation is Stage 3")

    budget = goal.budget
    max_iterations = min(budget.get("max_iterations", HARD_MAX_ITERATIONS), HARD_MAX_ITERATIONS)
    if max_steps is not None:
        max_iterations = min(max_iterations, max_steps)
    max_wall_clock = min(
        budget.get("max_wall_clock_sec", HARD_MAX_WALL_CLOCK_SEC), HARD_MAX_WALL_CLOCK_SEC
    )
    max_lab_actions = min(budget.get("max_lab_actions", HARD_MAX_LAB_ACTIONS), HARD_MAX_LAB_ACTIONS)

    started_at = time.monotonic()
    observations: dict = {}
    history: list[dict] = []
    plan: list[dict] = []
    escalations: list[str] = []
    iterations = 0
    lab_actions = 0
    stop_reason = "no_runnable_phase"

    while True:
        if iterations >= max_iterations:
            stop_reason = (
                "hard_cap"
                if budget.get("max_iterations", 0) >= HARD_MAX_ITERATIONS
                else "budget_exhausted"
            )
            break
        if time.monotonic() - started_at >= max_wall_clock:
            stop_reason = (
                "hard_cap"
                if budget.get("max_wall_clock_sec", 0) >= HARD_MAX_WALL_CLOCK_SEC
                else "budget_exhausted"
            )
            break
        if lab_actions >= max_lab_actions:
            stop_reason = (
                "hard_cap"
                if budget.get("max_lab_actions", 0) >= HARD_MAX_LAB_ACTIONS
                else "budget_exhausted"
            )
            break
        if goal.stop_when and _check_goal_stop(goal.stop_when, observations):
            stop_reason = "goal_met"
            break

        decision = decide_next_action(goal, observations, history, workspace=workspace)
        if decision.get("outcome") == "no_applicable_capability":
            stop_reason = "no_applicable_capability"
            break

        target = goal.targets[0] if goal.targets else ""
        if target and not enforce_scope(target, goal.scope):
            escalations.append(f"out_of_scope_action:{target}")
            stop_reason = "escalated:out_of_scope_action"
            break

        plan.append(decision)
        history.append(decision)
        observations = {**observations, **decision.get("expected_observation_delta", {})}
        lab_actions += 1
        iterations += 1

    report = {
        "status": "completed",
        "mode": "goal_dryrun",
        "goal_intent": goal.intent,
        "goal_role": goal.role,
        "plan": plan,
        "stop_reason": stop_reason,
        "iterations": iterations,
        "lab_actions": lab_actions,
        "escalations": escalations,
        "observations": observations,
    }

    with contextlib.suppress(Exception):
        journal.record_engagement(
            chain_result={
                "chain_depth": len(plan),
                "tools_called": [
                    {"tool": p.get("tool"), "arguments": p.get("args", {})} for p in plan
                ],
                "verified": False,
                "compromise_confirmed": False,
            },
            scenario={"category": f"goal:{goal.role}", "goal": goal.intent, "mode": "goal_dryrun"},
            engagement_id=f"goal-{goal.role}-{int(started_at)}",
        )

    return report


def _check_goal_stop(stop_when: list[dict], observations: dict) -> bool:
    for cond in stop_when:
        field_name = cond.get("field", "")
        expected = cond.get("equals")
        if field_name in observations and observations[field_name] == expected:
            return True
    return False


def resume_engagement(
    engagement_id: str,
    *,
    lab_exec: bool = False,
    dry_run: bool = False,
    notify_on_success: bool = False,
) -> dict:
    """Load a checkpoint and continue the engagement from where it stopped.

    Resume does NOT reset budget/hard-cap accounting (state.iterations,
    state.lab_actions, and state.started_at all round-trip through the
    checkpoint) and does NOT re-authorize an out-of-scope escalation — the
    same enforce_scope/_check_escalate calls run again on the next iteration,
    so a resumed engagement that still targets an out-of-scope action
    escalates again rather than proceeding.
    """
    cp_path = CHECKPOINT_DIR / f"{engagement_id}.json"
    if not cp_path.exists():
        return {"status": "error", "reason": f"checkpoint not found: {engagement_id}"}

    data = json.loads(cp_path.read_text())
    state = EngagementState.from_dict(data)

    pb = load_playbook(state.playbook_name)
    prior = journal.recall(
        scenario_category=pb.get("name", ""),
        keywords=[pb.get("name", "")],
    )

    if dry_run:
        return _dry_run_report(pb, state, prior)

    return _run_loop(pb, state, prior, lab_exec, None, False, notify_on_success)
