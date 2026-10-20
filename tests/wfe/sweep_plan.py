"""Write the queue sweep plan (root-fix P5-A3).

    uv run python -m tests.wfe.sweep_plan

Challengers come from ``candidate_queue.yaml``. Each one is placed only in an
intended workspace that a ``*_decision_v1.yaml`` plan gives an incumbent, that
``backends.yaml`` ``workspace_routing`` serves, and whose ``ctxNk`` window is at
least that workspace's ``context_limit``. The same inputs always write the same
plan.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

from portal.platform.inference.config import effective_workspace

REPO = Path(__file__).resolve().parents[2]
QUEUE = Path(__file__).with_name("candidate_queue.yaml")
PLANS = Path(__file__).with_name("plans")
OUT = PLANS / "sweep_from_queue_v1.yaml"
_WINDOW = re.compile(r"ctx(\d+)k")


def window_tokens(tag: str) -> int | None:
    """Tokens advertised by a ``-ctxNk`` tag, or None when the tag names none."""
    found = _WINDOW.search(tag)
    return int(found.group(1)) * 1024 if found else None


def servable(workspace: str, backends: dict) -> set[str]:
    """Model tags the base workspace's routed backend groups serve."""
    base_id = workspace.partition("::")[0]
    groups = set((backends.get("workspace_routing") or {}).get(base_id) or [])
    tags: set[str] = set()
    for be in backends.get("backends") or []:
        if be.get("group") not in groups:
            continue
        for model in be.get("models") or []:
            tags.add(str(model["id"] if isinstance(model, dict) else model))
        tags.update(be.get("aliases") or {})
    return tags


def incumbents(plans_dir: Path) -> dict[str, dict]:
    """workspace -> the decision plan's incumbent and the suites it is measured on.

    Two plans naming one workspace is refused: the sweep would not know which
    incumbent is the baseline.
    """
    found: dict[str, dict] = {}
    clashes: list[str] = []
    for path in sorted(plans_dir.glob("*_decision_v1.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        for ws, wl in (data.get("workloads") or {}).items():
            arms = wl.get("arms") or {}
            if ws in found:
                clashes.append(f"{ws} is in {found[ws]['plan']} and {path.name}")
                continue
            found[ws] = {
                "incumbent": arms.get("incumbent"),
                "tool_mode": wl.get("tool_mode"),
                "home": wl.get("home"),
                "discovery": list(wl.get("discovery") or []),
                "plan": path.name,
            }
    if clashes:
        raise ValueError("; ".join(clashes))
    return found


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _backends() -> dict:
    return _load_yaml(REPO / "config" / "backends.yaml")


def _portal_workspaces() -> dict:
    return (_load_yaml(REPO / "config" / "portal.yaml")).get("workspaces") or {}


def _reject(model: str, entry: dict, ws: str, seat: dict, backends: dict, portal: dict) -> str:
    """Why ``model`` is not a challenger in ``ws``, or '' when it is."""
    if not entry.get("available", True):
        return "unavailable"
    if model == seat.get("incumbent"):
        return "it is the incumbent"
    if model not in servable(ws, backends):
        return f"not served by {ws}'s workspace_routing groups"
    try:
        limit = effective_workspace(portal, ws).get("context_limit")
    except (KeyError, TypeError):
        limit = None
    window = window_tokens(model)
    if not isinstance(limit, int):
        return "workspace context_limit is missing"
    if window is None:
        return "tag has no ctxNk window"
    if window < limit:
        return f"window {window} < context_limit {limit}"
    return ""


def generate(
    queue_path: Path = QUEUE,
    plans_dir: Path = PLANS,
    backends: dict | None = None,
    portal: dict | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """(plan, notes). One workload per intended workspace that has an incumbent."""
    backends = _backends() if backends is None else backends
    portal = _portal_workspaces() if portal is None else portal
    queue = (_load_yaml(queue_path)).get("models") or {}
    seats = incumbents(plans_dir)
    notes: list[str] = []
    workloads: dict[str, dict] = {}
    intended = sorted({ws for entry in queue.values() for ws in (entry.get("intended") or [])})
    for ws in intended:
        seat = seats.get(ws)
        if seat is None or not seat.get("incumbent"):
            for model, entry in sorted(queue.items()):
                if ws in (entry.get("intended") or []):
                    notes.append(f"{ws}: {model} left out: no decision-plan incumbent")
            continue
        challengers: list[str] = []
        for model, entry in sorted(queue.items()):
            if ws not in (entry.get("intended") or []):
                continue
            why = _reject(model, entry, ws, seat, backends, portal)
            if why:
                notes.append(f"{ws}: {model} left out: {why}")
            else:
                challengers.append(model)
        if not challengers:
            notes.append(f"{ws}: no eligible queued challenger; the incumbent alone is confirmed")
        workloads[ws] = {
            "tool_mode": seat["tool_mode"],
            "home": seat["home"],
            "discovery": seat["discovery"],
            "arms": {"incumbent": seat["incumbent"], "challengers": challengers},
        }
    return {"workloads": workloads}, sorted(notes)


def render(plan: dict, notes: list[str]) -> str:
    """The plan file text. Notes ride in the document; ``expand_matrix`` ignores them."""
    doc = {"notes": notes, "workloads": plan["workloads"]}
    body = yaml.safe_dump(doc, sort_keys=False, width=4096)
    return (
        "# Sweep plan generated from tests/wfe/candidate_queue.yaml by tests.wfe.sweep_plan.\n"
        "# Incumbents come from tests/wfe/plans/*_decision_v1.yaml. A queued model is a\n"
        "# challenger only in an intended workspace whose workspace_routing groups serve\n"
        "# it and whose ctxNk window is at least that workspace's context_limit.\n" + body
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--queue", type=Path, default=QUEUE)
    ap.add_argument("--plans", type=Path, default=PLANS)
    args = ap.parse_args()
    plan, notes = generate(args.queue, args.plans)
    args.out.write_text(render(plan, notes))
    print(f"wrote {args.out}")
    for note in notes:
        print(note)
    print(f"workloads: {len(plan['workloads'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
