"""Seat-fit report: every production seat's projected bytes beside the standard stack.

Enumerates the production workspace seats (base hints and declared variants, not
bench lanes), resolves each hint's oMLX native id through the registry, and asks
the load guard to measure each footprint against the budget that remains when
every evictable resident is reclaimed. ``over_budget`` is that live snapshot;
``never_fit`` needs a fixed ``LOAD_GUARD_CEILING_GB``, because the balanced
tier's ceiling follows host free memory (P5-OMLX-CEILING-001) — without one the
same seat answers differently through the day and "never" is not a claim the
data supports. Seats are listed, not changed; ``stack_down_only`` is the
operator's existing declaration of a seat that only loads with the stack down.
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


def _working_set_budget_gib(report: dict[str, Any], uses_omlx: bool) -> float | None:
    """Budget for a working set: oMLX prefill-safe room when oMLX models participate."""
    available = report.get("available_gib")
    if not uses_omlx:
        return float(available) if isinstance(available, (int, float)) else None
    ceiling = report.get("ceiling_gib")
    zone = report.get("omlx_prefill_zone")
    margin = float(report.get("margin_gib") or 0.0)
    if isinstance(ceiling, (int, float)) and isinstance(zone, (int, float)) and zone > 0:
        return float(ceiling) * float(zone) - margin
    return float(available) if isinstance(available, (int, float)) else None


def _working_set_rows(report: dict[str, Any], working_sets: dict[str, Any]) -> list[dict[str, Any]]:
    by_seat = {str(row.get("seat") or ""): row for row in (report.get("seats") or [])}
    out: list[dict[str, Any]] = []
    for set_id, raw in working_sets.items():
        members = (
            list(raw.workspaces)
            if hasattr(raw, "workspaces")
            else list(raw.get("workspaces") or [])
        )
        mode = str(raw.mode if hasattr(raw, "mode") else raw.get("mode", "co_resident"))
        distinct: dict[tuple[str, str], float] = {}
        unknown: list[str] = []
        uses_omlx = False
        for seat_id in members:
            row = by_seat.get(seat_id)
            if row is None or not row.get("served"):
                unknown.append(seat_id)
                continue
            omlx_model = row.get("omlx_model")
            omlx_gib = row.get("omlx_projected_gib")
            if omlx_model and isinstance(omlx_gib, (int, float)):
                uses_omlx = True
                distinct[("omlx", str(omlx_model))] = float(omlx_gib)
            else:
                ollama_gib = row.get("ollama_projected_gib")
                if isinstance(ollama_gib, (int, float)):
                    distinct[("ollama", str(row.get("model") or seat_id))] = float(ollama_gib)
                else:
                    unknown.append(seat_id)
        budget = _working_set_budget_gib(report, uses_omlx)
        projected = None if unknown else sum(distinct.values())
        fits = None if projected is None or budget is None else bool(projected <= budget)
        out.append(
            {
                "working_set": str(set_id),
                "mode": mode,
                "workspaces": members,
                "models": [f"{eng}:{name}" for eng, name in distinct],
                "projected_gib": projected,
                "budget_gib": budget,
                "fits": fits,
                "unknown": unknown,
            }
        )
    return out


def annotate(
    report: dict[str, Any], *, working_sets: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Cross-check the fit verdicts against the operator's declarations."""
    rows = report.get("seats") or []
    report["undeclared_never_fit"] = [
        r["seat"] for r in rows if r["never_fit"] and not r["stack_down_only"]
    ]
    report["undeclared_over_budget"] = [
        r["seat"] for r in rows if r["over_budget"] and not r["stack_down_only"]
    ]
    report["unserved"] = [r["seat"] for r in rows if not r["served"]]
    declared = load_portal_config().working_sets if working_sets is None else working_sets
    ws_rows = _working_set_rows(report, declared)
    report["working_sets"] = ws_rows
    report["over_budget_working_sets"] = [
        r["working_set"] for r in ws_rows if r["mode"] == "co_resident" and r["fits"] is False
    ]
    return report
