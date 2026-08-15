"""bully.orchestrator -- LOOP, the only module that sequences a hunt iteration.

Stub at P1.0: exceptions + the public function signatures the CLI shell
(`commands/hunt_modes.py`) and `bully/__init__.py::run_hunt` delegate to.
Full stage-machine implementation lands in P1.7 (see
coding_task/bully/tasks/TASK_BULLY_P1_SPINE_V1.md P1.7).
"""

from __future__ import annotations

from typing import Any


class HonestBlockedError(RuntimeError):
    """A hunt/iteration is blocked by an infra/gate failure -- never a silent pass.

    MASTER SS8: gate-infrastructure failure is retryable BLOCKED, distinct
    from a gate that ran and failed. Both surface through this exception at
    the CLI boundary; the distinction is carried in the message/rationale.
    """


class OperatorRequiredError(RuntimeError):
    """Raised when a `[GATE]` command is invoked by a non-operator actor.

    Hunt authorization (`hunt run`) and resume-after-block (`hunt resume`)
    are operator-only (MASTER SS7 operator-confirmation index).
    """


def _require_operator(actor: str) -> None:
    if not actor.startswith("operator:"):
        raise OperatorRequiredError(
            f"actor {actor!r} is not an operator; hunt authorization requires actor='operator:<id>'"
        )


def run_hunt(
    *, neighborhood: str = "auto", budget_class: str = "default", dry_run: bool = False, actor: str
) -> dict[str, Any]:
    """`hunt run` -- authorize + drive a new hunt through the LOOP stage machine.

    [GATE] operator-only (I-3 operator boundary). Full stage-machine
    implementation lands in P1.7.
    """
    _require_operator(actor)
    raise NotImplementedError("orchestrator.run_hunt lands in P1.7")


def resume_hunt(hunt_id: str, *, actor: str) -> dict[str, Any]:
    """`hunt resume` -- resume a blocked/interrupted hunt. [GATE] operator-only."""
    _require_operator(actor)
    raise NotImplementedError("orchestrator.resume_hunt lands in P1.7")


def hunt_status(hunt_id: str) -> dict[str, Any]:
    """`hunt status` -- read-only report; no operator gate."""
    raise NotImplementedError("orchestrator.hunt_status lands in P1.7")


def cancel_hunt(hunt_id: str, *, actor: str, reason: str = "") -> dict[str, Any]:
    """`hunt cancel` -- revokes leases, never deletes evidence."""
    _require_operator(actor)
    raise NotImplementedError("orchestrator.cancel_hunt lands in P1.7")


def hunt_doctor() -> dict[str, Any]:
    """`hunt doctor` -- SUB integrity check (P1.2)."""
    raise NotImplementedError("orchestrator.hunt_doctor lands in P1.2")


def queue_resolve(*, item_id: str | None, actor: str, rationale: str = "") -> dict[str, Any]:
    """`hunt queue --confirm <id>` -- promotion-queue resolution. [GATE] operator-only (P2)."""
    _require_operator(actor)
    raise NotImplementedError("orchestrator.queue_resolve lands in P2")
