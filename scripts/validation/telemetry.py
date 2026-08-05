"""Telemetry-family checks: the complexity census advisory."""

from __future__ import annotations

import sys

from ._shared import REPO_ROOT
from .registry import register


@register(
    "complexity_census", "BU. complexity census ratchet (totals vs recorded budget)", order=71
)
def check_complexity_census() -> tuple[str, str, list[dict]]:
    """BU. Complexity census — enforcing delta vs the recorded budget.

    The complexity ratchet: `scripts/complexity_report.py --gate` fails when
    any gated total (data_lines, god_funcs, god_lines, prose, unwired_scripts,
    identical_pairs, committed_blob_bytes) exceeds `config/complexity_budget.yaml`.
    The budget records achieved lows and only ratchets down. This check was
    advisory until C7 of TASK_PORTAL_SIMPLIFY_V1 locked it into a failing gate —
    it is no longer unconditional, because the budget is the ratchet.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from complexity_report import gate, run_census

        rc = gate(run_census())
        if rc == 0:
            return ("PASS", "all complexity totals at or below the recorded budget", [])
        return ("FAIL", "complexity increased above config/complexity_budget.yaml", [])
    except Exception as e:  # noqa: BLE001
        return ("FAIL", f"complexity census unavailable: {type(e).__name__}: {e}", [])
