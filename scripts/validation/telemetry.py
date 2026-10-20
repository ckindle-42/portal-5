"""Telemetry-family checks: the complexity census ceiling."""

from __future__ import annotations

import sys

from ._shared import REPO_ROOT
from .registry import register


@register("complexity_census", "BU. complexity ceilings (census totals vs ceilings)", order=71)
def check_complexity_census() -> tuple[str, str, list[dict]]:
    """BU. Complexity ceilings — census totals vs the operator-set ceilings.

    `scripts/complexity_report.py --gate` fails when any gated total
    (data_lines, god_lines, unwired_scripts, identical_pairs,
    committed_blob_bytes) exceeds its ceiling in
    `config/complexity_budget.yaml`. prose and god_funcs are reported by the
    same run and never compared. Each ceiling carries a `reason:` and is raised
    only by an operator; nothing re-stamps the file automatically.
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from complexity_report import gate, run_census

        rc = gate(run_census())
        if rc == 0:
            return ("PASS", "all complexity totals within the declared ceilings", [])
        return ("FAIL", "a complexity total exceeded config/complexity_budget.yaml", [])
    except Exception as e:  # noqa: BLE001
        return ("FAIL", f"complexity census unavailable: {type(e).__name__}: {e}", [])
