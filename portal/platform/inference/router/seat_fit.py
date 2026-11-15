"""Seat-fit report: every production seat's projected bytes beside the standard stack.

Enumerates the production workspace seats (base hints and declared variants, not
bench lanes), resolves each hint's oMLX native id through the registry, and asks
the load guard to measure each footprint against the budget that remains when
every evictable resident is reclaimed. Seats that can never fit are listed, not
changed; ``stack_down_only`` is the operator's existing declaration of that fact.
"""

from __future__ import annotations

from typing import Any

from portal.platform.inference.config import load_portal_config
from portal.platform.inference.router.workspaces import WORKSPACES


def _seat(seat_id: str, hint: str, stack_down_only: Any, registry: Any) -> dict[str, Any]:
    omlx_model = None
    for backend in registry.list_backends():
        if backend.type != "omlx":
            continue
        resolved = backend.resolve_model(hint)
        if resolved is not None:
            omlx_model = resolved
            break
    return {
        "seat": seat_id,
        "model": hint,
        "omlx_model": omlx_model,
        "stack_down_only": bool(stack_down_only),
    }


def production_seats(registry: Any) -> list[dict[str, Any]]:
    """One row per production seat: workspace base hints and declared variants."""
    specs = load_portal_config().workspaces
    seats: list[dict[str, Any]] = []
    for ws_id, ws in WORKSPACES.items():
        if ws_id.startswith("bench-"):
            continue
        hint = str(ws.get("model_hint") or "")
        if hint:
            seats.append(_seat(ws_id, hint, ws.get("stack_down_only"), registry))
        spec = specs.get(ws_id)
        for name, variant in spec.variants.items() if spec is not None else {}.items():
            vhint = str(variant.get("model_hint") or "")
            if vhint:
                seats.append(
                    _seat(f"{ws_id}::{name}", vhint, variant.get("stack_down_only"), registry)
                )
    return seats


def annotate(report: dict[str, Any]) -> dict[str, Any]:
    """Cross-check the fit verdicts against the operator's declarations."""
    rows = report.get("seats") or []
    report["undeclared_never_fit"] = [
        r["seat"] for r in rows if r["never_fit"] and not r["stack_down_only"]
    ]
    report["unserved"] = [r["seat"] for r in rows if not r["served"]]
    return report
