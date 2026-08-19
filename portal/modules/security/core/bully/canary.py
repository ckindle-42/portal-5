"""bully.canary -- held-out contamination canary + write-back freeze
(TASK_BULLY_RELATE_AND_INVESTIGATE_V1 G.3, guards silent drift as the
library grows).

A purely external ground-truth set never enters the anchor library.
Accuracy on it is re-measured after each anchor-growth interval; if
in-library accuracy improves while held-out accuracy degrades, the system
is learning itself -- that's a contamination finding, and write-back
freezes until diagnosed (never a quiet continue). The compounding
measurement (M.3) uses only this external ground truth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class CanaryViolationError(RuntimeError):
    """A held-out canary record was about to be written back as an anchor."""


class WriteBackFrozenError(RuntimeError):
    """Anchor write-back is frozen pending a contamination diagnosis."""


@dataclass(frozen=True)
class CanarySet:
    protected_record_ids: frozenset[str]

    def contains(self, record_id: str) -> bool:
        return record_id in self.protected_record_ids


def guard_write_back(canary: CanarySet, record_id: str) -> None:
    """Raise before a held-out record is ever written back as an anchor."""
    if canary.contains(record_id):
        raise CanaryViolationError(
            f"held-out canary record {record_id!r} must never be written back as an anchor"
        )


@dataclass(frozen=True)
class ContaminationReport:
    contaminated: bool
    library_delta: float
    heldout_delta: float

    @property
    def freeze_write_back(self) -> bool:
        return self.contaminated


def check_contamination(
    *,
    library_accuracy_before: float,
    library_accuracy_after: float,
    heldout_accuracy_before: float,
    heldout_accuracy_after: float,
) -> ContaminationReport:
    """In-library performance improving while the *external* held-out set
    degrades means the system learned itself, not the world (G.3)."""
    library_delta = library_accuracy_after - library_accuracy_before
    heldout_delta = heldout_accuracy_after - heldout_accuracy_before
    contaminated = library_delta > 0 and heldout_delta < 0
    return ContaminationReport(
        contaminated=contaminated, library_delta=library_delta, heldout_delta=heldout_delta
    )


@dataclass
class WriteBackGate:
    """Wraps a write-back callable with the canary guard and a freeze
    switch a contamination finding can throw (and only an explicit
    diagnosis can clear)."""

    canary: CanarySet
    write_fn: Callable[..., Any]
    frozen: bool = False
    freeze_reason: str | None = field(default=None)

    def freeze(self, reason: str) -> None:
        self.frozen = True
        self.freeze_reason = reason

    def unfreeze(self) -> None:
        self.frozen = False
        self.freeze_reason = None

    def write(self, record_id: str, *args: Any, **kwargs: Any) -> Any:
        if self.frozen:
            raise WriteBackFrozenError(self.freeze_reason or "write-back frozen")
        guard_write_back(self.canary, record_id)
        return self.write_fn(*args, **kwargs)
