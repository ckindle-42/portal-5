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

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import field_journal as journal
from . import oracles as oracle_mod
from .playbooks import load_playbook, resolve_phases, validate_playbook

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
        return "hard_cap" if budget.get("max_iterations", 0) <= HARD_MAX_ITERATIONS else "budget_exhausted"

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
            if trigger == "out_of_scope_action" and "out_of_scope_action" in state.escalations:
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
        f.get("oracle_attempts", 0) - f.get("oracle_successes", 0)
        for f in state.findings
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

    return _run_loop(pb, state, prior, lab_exec, workspace, auto_continue_safe)


def _run_loop(
    pb: dict,
    state: EngagementState,
    prior: list[dict],
    lab_exec: bool,
    workspace: str | None,
    auto_continue_safe: bool,
) -> dict:
    """Execute the engagement loop (real execution)."""
    while True:
        # Budget check
        budget_stop = _check_budget(state, pb)
        if budget_stop:
            _write_checkpoint(state, budget_stop)
            return _build_report(state, pb, prior, budget_stop)

        # Stop condition check
        if _check_stop(pb, state.observations):
            _write_checkpoint(state, "goal_met")
            return _build_report(state, pb, prior, "goal_met")

        # Escalation check
        escalation = _check_escalate(state, pb)
        if escalation:
            if (
                escalation == "out_of_scope_action"
                or not auto_continue_safe
            ):
                state.escalations.append(escalation)
                _write_checkpoint(state, f"escalated:{escalation}")
                return _build_report(state, pb, prior, f"escalated:{escalation}")

        # Resolve runnable phases
        ready = resolve_phases(pb, state.observations)
        if not ready:
            _write_checkpoint(state, "no_runnable_phase")
            return _build_report(state, pb, prior, "no_runnable_phase")

        # Execute the first ready phase (simplified — real version loops all ready phases)
        phase = ready[0]
        pid = phase.get("id", f"phase-{state.iterations}")

        if phase.get("manual"):
            state.escalations.append(f"manual_phase:{pid}")
            _write_checkpoint(state, f"escalated:manual_phase:{pid}")
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
        state.findings.append({
            "oracle": oracle_id,
            "verified": verdict.verified,
            "evidence": verdict.evidence[:500],
            "oracle_attempts": verdict.required,
            "oracle_successes": verdict.reproductions,
        })


def _dry_run_report(pb: dict, state: EngagementState, prior: list[dict]) -> dict:
    """Build a dry-run engagement plan."""
    phases_plan = []
    for phase in pb.get("phases", []):
        phases_plan.append({
            "id": phase.get("id", "?"),
            "manual": phase.get("manual", False),
            "depends_on": phase.get("depends_on", []),
            "steps": len(phase.get("steps", [])),
        })

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


def _build_report(
    state: EngagementState, pb: dict, prior: list[dict], stop_reason: str
) -> dict:
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
    try:
        journal.record_engagement(
            chain_result={
                "chain_depth": len(state.completed_phases),
                "tools_called": state.findings,
                "verified": any(f.get("verified") for f in state.findings),
                "compromise_confirmed": any(
                    f.get("verified") for f in state.findings
                ),
            },
            scenario={"category": pb.get("name", "loop"), "goal": stop_reason},
            engagement_id=state.engagement_id,
        )
    except Exception:
        pass

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


def resume_engagement(
    engagement_id: str,
    *,
    lab_exec: bool = False,
    dry_run: bool = False,
) -> dict:
    """Load a checkpoint and continue the engagement from where it stopped."""
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

    return _run_loop(pb, state, prior, lab_exec, None, False)
