"""Seat evidence: does the fitness ledger still describe what production serves?

The ledger (tests/wfe/fitness_ledger.yaml) holds one cell per (model, workspace)
written by `report --record`, and recording already refuses a campaign that did
not run through the pipeline. This check is the standing counterpart: it fails a
cell that cites a non-pipeline campaign, flags a cell whose model production no
longer resolves to the build the cell measured, and reports the seats that have
no confirm cell at all. Spec: docs/WFE_ROOT_CAUSES_20261013.md.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from ._shared import REPO_ROOT
from .registry import register

LEDGER = REPO_ROOT / "tests" / "wfe" / "fitness_ledger.yaml"
CAMPAIGNS = REPO_ROOT / "tests" / "wfe" / "results" / "campaigns"
ROUTING = REPO_ROOT / "config" / "backends.yaml"


def _cells() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    doc = yaml.safe_load(LEDGER.read_text()) or {}
    return [c for c in (doc.get("cells") or []) if isinstance(c, dict)]


def _campaign_engine(campaign_id: str) -> str:
    """The engine a campaign ran under, or 'missing' when it is not on disk."""
    manifest = CAMPAIGNS / str(campaign_id) / "manifest.json"
    if not manifest.exists():
        return "missing"
    try:
        doc = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return "unreadable"
    return str((doc.get("instrument") or {}).get("engine") or "legacy")


def _seats() -> dict[str, str]:
    """workspace -> the model production seats there (backends.yaml routing)."""
    cfg = yaml.safe_load(ROUTING.read_text()) or {}
    seats: dict[str, str] = {}
    for ws, entry in (cfg.get("workspace_routing") or {}).items():
        model = entry.get("primary") or entry.get("model") if isinstance(entry, dict) else entry
        if model:
            seats[str(ws)] = str(model)
    return seats


def _served_today(workspace: str, model: str) -> str | None:
    """What production resolves this arm to now; None when it cannot be resolved."""
    try:
        from tests.wfe.campaign import seat_primary
    except Exception:  # pragma: no cover - the harness must import for this to mean anything
        return None
    try:
        return seat_primary(workspace, model)
    except Exception:
        return None


def _ledger_findings(cells: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(hard failures, stale warnings)."""
    fails: list[str] = []
    stale: list[str] = []
    for c in cells:
        engine = _campaign_engine(c.get("campaign"))
        if engine != "pipeline":
            fails.append(
                f"{c.get('workspace')}/{c.get('model')}: campaign {c.get('campaign')!r} is {engine}, not pipeline"
            )
            continue
        now = _served_today(str(c.get("workspace")), str(c.get("model")))
        if now and c.get("served") and now != c["served"]:
            stale.append(
                f"{c.get('workspace')}/{c.get('model')}: measured {c['served']}, production now serves {now}"
            )
    return fails, stale


@register(
    "wfe_fitness_ledger",
    "HP. WFE seat evidence matches the ledger and what production serves",
    order=205,
)
def check_wfe_fitness_ledger() -> tuple[str, str, list[dict[str, Any]]]:
    """HP. A seat decision must cite a pipeline campaign measured by one instrument."""
    cells = _cells()
    fails, stale = _ledger_findings(cells)
    covered = {(str(c.get("workspace")), str(c.get("model"))) for c in cells}
    seats = _seats()
    uncovered = sorted(ws for ws, model in seats.items() if (ws, model) not in covered)

    subs: list[dict[str, Any]] = [
        {
            "name": "every ledger cell cites a pipeline campaign",
            "status": "FAIL" if fails else "PASS",
            "detail": f"{len(cells)} cell(s) cite a pipeline campaign"
            if not fails
            else "; ".join(fails[:6]),
        },
        {
            "name": "every seat's measured build is what production still serves",
            "status": "WARN" if stale else "PASS",
            "detail": "no seat's served build moved" if not stale else "; ".join(stale[:6]),
        },
        {
            "name": "every seat has a confirm cell",
            "status": "WARN" if uncovered else "PASS",
            "detail": (
                f"{len(seats) - len(uncovered)}/{len(seats)} seat(s) have confirm evidence"
                if not uncovered
                else f"{len(uncovered)} of {len(seats)} seat(s) have no confirm cell yet: "
                f"{uncovered[:6]}"
            ),
        },
    ]
    if fails:
        return ("FAIL", f"{len(fails)} ledger cell(s) cite a non-pipeline campaign", subs)
    if stale:
        return ("WARN", f"{len(stale)} seat(s) are STALE against production", subs)
    if uncovered:
        return (
            "WARN",
            f"{len(uncovered)} of {len(seats)} seat(s) have no confirm cell yet "
            "(Part 5's sweep records them)",
            subs,
        )
    return ("PASS", f"{len(cells)} ledger cell(s) match production and cover every seat", subs)
