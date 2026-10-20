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
import os
from pathlib import Path
from typing import Any

import yaml

from ._shared import REPO_ROOT
from .registry import register

LEDGER = Path(os.environ.get("WFE_FITNESS_LEDGER") or REPO_ROOT / "tests/wfe/fitness_ledger.yaml")
DATA_ROOT = Path(os.environ.get("PORTAL_DATA_ROOT", str(Path.home() / "AI_Output" / "portal-data")))
CAMPAIGNS = DATA_ROOT / "tests" / "wfe" / "results" / "campaigns"
ROUTING = REPO_ROOT / "config" / "backends.yaml"
PORTAL = REPO_ROOT / "config" / "portal.yaml"


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
    """workspace -> the model production seats there. backends.yaml says which
    workspaces production routes, but its workspace_routing maps each one to
    backend groups, not to a model; the seat is portal.yaml's model_hint."""
    routed = (yaml.safe_load(ROUTING.read_text()) or {}).get("workspace_routing") or {}
    spaces = (yaml.safe_load(PORTAL.read_text()) or {}).get("workspaces") or {}
    return {
        str(ws): str(spaces[ws]["model_hint"])
        for ws in routed
        if (spaces.get(ws) or {}).get("model_hint")
    }


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


def _content_today(backend: str, model: str) -> tuple[str, str]:
    """The content id of the build that serves `model` now, or ("", why not)."""
    try:
        from tests.wfe.campaign import observe_identity
    except Exception as e:  # pragma: no cover
        return "", f"the harness does not import ({e})"
    ident, why = observe_identity(backend, model)
    return ident["content"], why


def _stale(where: str, workspace: str, model: str, served: dict) -> list[str]:
    """Why this cell no longer describes what production serves, if it does not."""
    now = _served_today(workspace, model)
    if not now:
        return []
    if now != served.get("model"):
        return [f"{where}: measured {served.get('model')}, production now serves {now}"]
    content, why = _content_today(str(served.get("backend") or ""), now)
    if not content:
        return [f"{where}: cannot observe the build production serves now ({why})"]
    if content != served.get("content"):
        return [f"{where}: {now} was rebuilt since it was measured"]
    return []


def _ledger_findings(cells: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(hard failures, stale or unobservable warnings)."""
    fails: list[str] = []
    stale: list[str] = []
    for c in cells:
        where = f"{c.get('workspace')}/{c.get('model')}"
        engine = _campaign_engine(c.get("campaign"))
        served = c.get("served") if isinstance(c.get("served"), dict) else {}
        if engine != "pipeline":
            fails.append(f"{where}: campaign {c.get('campaign')!r} is {engine}, not pipeline")
        elif not served.get("content"):
            fails.append(f"{where}: no served identity recorded, so it cannot be checked")
        else:
            stale += _stale(where, str(c.get("workspace")), str(c.get("model")), served)
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
    # A seat is covered by a cell it won (model) or a cell it defended (incumbent).
    covered = {
        (str(c.get("workspace")), str(c.get(k))) for c in cells for k in ("model", "incumbent")
    }
    seats = _seats()
    uncovered = sorted(ws for ws, model in seats.items() if (ws, model) not in covered)

    subs: list[dict[str, Any]] = [
        {
            "name": "every ledger cell cites a pipeline campaign",
            "status": "FAIL" if fails else "PASS",
            "detail": f"{len(cells)} cell(s) cite a pipeline campaign and a served identity"
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
        return ("FAIL", f"{len(fails)} ledger cell(s) are not decision evidence", subs)
    if stale:
        return ("WARN", f"{len(stale)} cell(s) are STALE or unobservable against production", subs)
    if uncovered:
        return (
            "WARN",
            f"{len(uncovered)} of {len(seats)} seat(s) have no confirm cell yet "
            "(Part 5's sweep records them)",
            subs,
        )
    return ("PASS", f"{len(cells)} ledger cell(s) match production and cover every seat", subs)


@register(
    "serving_conformance",
    "HQ. Every served seat and installed tag conforms to its card and library template",
    order=206,
)
def check_serving_conformance() -> tuple[str, str, list[dict[str, Any]]]:
    """HQ. tests/wfe/settings_audit on the live fleet: each seat on the engine that actually
    serves it, plus template and stop hygiene on EVERY installed Ollama tag, so a model pulled
    for a bench or a challenger is checked the moment it lands rather than when a campaign
    trips over it (2026-10-18: ~30 raw-jinja tags, a wrong Laguna parser and bad stops were
    all found by hand). Any WARN or FAIL fails the check; INFO is reporting only. SKIP when
    Ollama is not reachable (no live fleet to audit)."""
    import urllib.request

    from tests.wfe import settings_audit as audit

    try:
        urllib.request.urlopen(f"{audit.OLLAMA}/api/version", timeout=3).read()
    except Exception as e:  # noqa: BLE001
        return ("SKIP", f"Ollama not reachable at {audit.OLLAMA} ({e.__class__.__name__})", [])
    seats = audit.run_audit()
    backends = yaml.safe_load(ROUTING.read_text())
    tags = audit.audit_tags(sorted(audit.installed_tags(backends)))
    findings = [
        v for v in [*seats["violations"], *tags["violations"]] if v["severity"] in ("WARN", "FAIL")
    ]
    subs = [
        {
            "name": f"{v['workspace']}: {v['kind']}",
            "status": "FAIL",
            "detail": v["detail"][:240],
        }
        for v in findings
    ]
    if findings:
        kinds = sorted({v["kind"] for v in findings})
        return (
            "FAIL",
            f"{len(findings)} conformance finding(s) ({', '.join(kinds)}) — run "
            "`uv run python -m tests.wfe.settings_audit` and fix them",
            subs,
        )
    return (
        "PASS",
        f"{seats['checked_workspaces']} seat(s) and {tags['checked_tags']} installed tag(s) conform",
        subs,
    )
