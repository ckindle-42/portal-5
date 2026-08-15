"""Defensive Bully — autonomous purple-team hunt loop (additive package).

Public application API only. Internal modules (``store``, ``organ``,
``events``, ``outbox``, ``evidence``, ``signatures``, ``cousin_engine``,
``investigation``) are implementation details reached only through the
functions re-exported here or through ``bully/commands`` (CLI shell in
``portal/modules/security/core/commands/hunt_modes.py``).

Module roster and boundary rules: ``coding_task/bully/final/
FINAL_ARCHITECTURE_DEFENSIVE_BULLY.md`` SS1-2. Build program:
``coding_task/bully/tasks/TASK_BULLY_00_MASTER_V1.md``.

P1 lands the brain substrate: contracts -> store -> outbox -> evidence ->
organ -> signatures -> cousin engine -> investigation arm -> LOOP
orchestrator. Later phases (P2-P7) add BIN/HEART, mutation/drift,
discovery, handoff, and the training flywheel; their modules are stubbed
under this package but not implemented until their own phase lands.
"""

from __future__ import annotations

__all__ = [
    "__version__",
    "run_hunt",
]

__version__ = "0.1.0"


def run_hunt(*args: object, **kwargs: object) -> object:
    """Public entry point for starting/resuming a hunt (I-3).

    Thin re-export over ``orchestrator.py`` -- the only module that
    sequences a hunt iteration (MASTER SS3). Delegates lazily so that
    importing this package never pulls in the full orchestrator/store/
    organ dependency chain unless a hunt is actually run.
    """
    from .orchestrator import run_hunt as _run_hunt

    return _run_hunt(*args, **kwargs)
