"""bully.targeting -- TGT, recall-influenced target selection (P4.3, I-11).

Pure compute over injected data (MASTER SS3): no SQL, no network. `select`
takes a `HuntContext` snapshot (SUB: `open_cells` + `known_state_view`), a
`RecallReceipt` (ORG), and a `costing.CostView` (I-13) already assembled by
the caller (`orchestrator.py`) -- this module never fetches any of that
itself.

Two-stage filter, per I-11 FAILURE SEMANTICS:

1. **Hard eligibility** (never soft, never overridable except the one
   documented override path below): `UNAUTHORIZED` / `NOT_READY` /
   `UNHEALTHY` / `LOCKED` / `KNOWN_BENIGN`. A cell failing any of these is
   declined with a reason -- it never reaches ranking.
2. **Cost rankability**: a hard-eligible cell with no resolvable cost (I-13
   `CostView.units_for` reports a gap) is declined `MISSING_COST` --
   "unrankable", never assigned a zero/free cost.

Surviving cells get one posterior adjustment from VALIDATED/
OPERATOR_CONFIRMED `known_state` entries (DATA_MODEL SS1.7: "only
VALIDATED/OPERATOR_CONFIRMED adjusts priors"; "posterior_adjustment ...
never a second multiplier" -- at most one factor is ever applied per
cell), a recall-influence boost when the recall receipt's selected context
names the cell's subject, and a deterministic priority = value/cost
ordering with a fixed tie-break (`priority desc, then cell_id asc` -- pure
lexicographic, so two equal-priority cells always order the same way).

`[GATE]` override (I-11 OPERATOR BOUNDARY): "override requires a reason
and may not bypass authorization/readiness/telemetry hard gates." The only
override this module honors is forcing a `KNOWN_BENIGN`-declined cell back
into ranking (an operator's live judgment call, not a fabricated trial --
it is still subject to the same cost-rankability check as everything
else); an override naming a cell declined for `UNAUTHORIZED`/`NOT_READY`/
`UNHEALTHY` is rejected outright.
"""

from __future__ import annotations

import uuid
from typing import Any

from .contracts import DeclinedCell, TargetDecision

__all__ = ["select", "OverrideRejectedError"]

ALGORITHM_VERSION = "targeting-v1"

_UNOVERRIDABLE_HARD_GATES = frozenset({"UNAUTHORIZED", "NOT_READY", "UNHEALTHY"})

# Single-application posterior adjustment factors per known_state kind
# (DATA_MODEL SS1.7 "never a second multiplier" -- only the strongest
# matching VALIDATED/OPERATOR_CONFIRMED entry's factor is ever applied).
_POSTERIOR_ADJUSTMENTS: dict[str, float] = {
    "known_covered": 0.30,
    "known_defense": 0.30,
    "dead_end": 0.05,
    "disproved": 0.05,
    "recent_kill": 0.20,
    "blocked": 0.50,
    "contradicted": 0.50,
}

DEFAULT_RECALL_BOOST = 0.5


class OverrideRejectedError(ValueError):
    """Raised when an operator override targets a hard gate I-11 forbids
    bypassing (authorization/readiness/telemetry)."""


def _hard_gate_reason(
    cell: dict[str, Any], subject: str, known_state: list[dict[str, Any]]
) -> str | None:
    if not cell.get("authorized", True):
        return "UNAUTHORIZED"
    if not cell.get("ready", True):
        return "NOT_READY"
    if not cell.get("healthy", True):
        return "UNHEALTHY"
    if cell.get("locked", False):
        return "LOCKED"
    for ks in known_state:
        if ks.get("subject") == subject and ks.get("kind") == "known_benign":
            return "KNOWN_BENIGN"
    return None


def _posterior(cell: dict[str, Any], subject: str, known_state: list[dict[str, Any]]) -> float:
    base = float(cell.get("prior", 0.5))
    adjustment = 1.0
    for ks in known_state:
        if ks.get("subject") != subject:
            continue
        if ks.get("trust_tier") not in ("VALIDATED", "OPERATOR_CONFIRMED"):
            continue
        factor = _POSTERIOR_ADJUSTMENTS.get(ks.get("kind"))
        if factor is not None:
            adjustment = factor  # last matching validated entry wins -- never compounded
    return round(max(0.0, min(1.0, base * adjustment)), 4)


def _recall_subjects(recall: Any) -> set[str]:
    subjects: set[str] = set()
    selected = getattr(recall, "selected_context", None) or []
    for item in selected:
        record = item.get("record") if isinstance(item, dict) else None
        if isinstance(record, dict):
            subj = record.get("subject") or record.get("id")
            if subj:
                subjects.add(str(subj))
    return subjects


def select(
    context: Any,
    recall: Any,
    ledger: Any,
    *,
    recall_boost: float = DEFAULT_RECALL_BOOST,
    override: dict[str, Any] | None = None,
) -> TargetDecision:
    """I-11: `select(context, recall, ledger) -> TargetDecision`.

    `override`, when given, is `{"cell_id": ..., "reason": ...}` -- both
    required. It may only rescue a `KNOWN_BENIGN` decline back into
    ranking (still subject to the cost-rankability check); naming a cell
    declined for an authorization/readiness/telemetry hard gate raises
    `OverrideRejectedError` immediately.
    """
    if override is not None and not override.get("reason"):
        raise ValueError("[GATE] targeting override requires a reason")

    cells = list(getattr(context, "open_cells", None) or [])
    known_state = list(getattr(context, "known_state_view", None) or [])
    hunt_id = getattr(context, "hunt_id", None)
    config_version = getattr(context, "config_version", "unknown")

    declined: list[DeclinedCell] = []
    survivors: list[dict[str, Any]] = []
    override_cell_id = override.get("cell_id") if override else None

    for cell in cells:
        cell_id = cell["cell_id"]
        subject = cell.get("subject", cell_id)
        reason = _hard_gate_reason(cell, subject, known_state)
        if reason is None:
            survivors.append(cell)
            continue
        if cell_id == override_cell_id:
            if reason in _UNOVERRIDABLE_HARD_GATES:
                raise OverrideRejectedError(
                    f"[GATE] override cannot bypass hard gate {reason} for cell {cell_id!r}"
                )
            # KNOWN_BENIGN or LOCKED, overridden: rescued into ranking, but
            # the decline is still recorded (audit trail of what was
            # overridden and why -- I-11 PROVENANCE).
            declined.append(
                DeclinedCell(
                    cell_id=cell_id,
                    reason=reason,
                    detail=f"overridden by operator: {override['reason']}",
                )
            )
            survivors.append(cell)
            continue
        declined.append(DeclinedCell(cell_id=cell_id, reason=reason, detail=f"hard gate: {reason}"))

    decision_id = f"tgt-{uuid.uuid4().hex[:12]}"
    if not survivors:
        return TargetDecision(
            decision_id=decision_id,
            hunt_id=hunt_id,
            algorithm_version=ALGORITHM_VERSION,
            config_version=config_version,
            status="no_eligible_target",
            selected_cell_id=None,
            declined=tuple(declined),
        )

    recall_subjects = _recall_subjects(recall)
    ranked: list[dict[str, Any]] = []
    for cell in survivors:
        cell_id = cell["cell_id"]
        subject = cell.get("subject", cell_id)
        cost_ref = cell.get("cost_ref", hunt_id)
        units, gap = ledger.units_for(cost_ref)
        if gap:
            declined.append(
                DeclinedCell(
                    cell_id=cell_id,
                    reason="MISSING_COST",
                    detail=f"no resolvable cost data for {subject!r} (cost_ref={cost_ref!r})",
                )
            )
            continue
        posterior = _posterior(cell, subject, known_state)
        value = posterior
        influenced = subject in recall_subjects
        boost = recall_boost if influenced else 0.0
        cost_units = units if units and units > 0 else 0.0001  # avoid div-by-zero; never free
        priority = round((value / cost_units) * (1.0 + boost), 6)
        ranked.append(
            {
                "cell_id": cell_id,
                "subject": subject,
                "raw_features": {"prior": cell.get("prior", 0.5)},
                "posterior": posterior,
                "value": value,
                "cost": units,
                "priority": priority,
                "recall_influenced": influenced,
            }
        )

    if not ranked:
        return TargetDecision(
            decision_id=decision_id,
            hunt_id=hunt_id,
            algorithm_version=ALGORITHM_VERSION,
            config_version=config_version,
            status="unrankable",
            selected_cell_id=None,
            declined=tuple(declined),
        )

    ranked.sort(key=lambda r: (-r["priority"], r["cell_id"]))
    influenced_cells = [r["cell_id"] for r in ranked if r["recall_influenced"]]

    return TargetDecision(
        decision_id=decision_id,
        hunt_id=hunt_id,
        algorithm_version=ALGORITHM_VERSION,
        config_version=config_version,
        status="selected",
        selected_cell_id=ranked[0]["cell_id"],
        ordered_targets=tuple(ranked),
        declined=tuple(declined),
        recall_influence={
            "recall_id": getattr(recall, "recall_id", None),
            "influenced_cells": influenced_cells,
            "boost": recall_boost,
        },
        tie_break="priority_desc_then_cell_id_asc",
    )
