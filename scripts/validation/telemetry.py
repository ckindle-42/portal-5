"""Telemetry-family checks: the complexity census advisory."""

from __future__ import annotations

import sys

from ._shared import REPO_ROOT
from .registry import register


@register(
    "complexity_census", "BU. complexity census advisory (delta vs recorded budget)", order=71
)
def check_complexity_census() -> tuple[str, str, list[dict]]:
    """BU. Complexity census — advisory delta vs the recorded budget.

    ADVISORY UNTIL C7: this check computes the complexity census, prints the
    delta against `config/complexity_budget.yaml`, and returns OK
    unconditionally. It becomes a failing gate in Phase C7 of
    TASK_PORTAL_SIMPLIFY_V1, when the ratchet is locked. It is advisory by
    design rather than fake-severity: an honest unconditional pass beats a
    made-up severity level, and the budget itself is still tracked so the
    direction of travel is visible in every validation run.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from complexity_report import BUDGET_PATH, GATED_KEYS, run_census

        census = run_census()
        totals = census.totals
        budget = {}
        if BUDGET_PATH.exists():
            import yaml

            budget = yaml.safe_load(BUDGET_PATH.read_text()) or {}
        deltas = []
        for key in GATED_KEYS:
            allowed = budget.get(key)
            if allowed is None:
                continue
            delta = totals[key] - allowed
            deltas.append(f"{key}: {delta:+d}")
        detail = f"ADVISORY — delta vs budget: {'; '.join(deltas) or 'no budget file'}"
        return ("PASS", detail, [])
    except Exception as e:  # noqa: BLE001
        return ("PASS", f"ADVISORY — census unavailable: {type(e).__name__}: {e}", [])
