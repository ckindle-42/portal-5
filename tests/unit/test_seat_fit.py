"""Seat-fit report: every production seat measured against the standard-stack budget.

The report lists seats, it never changes them: ``over_budget`` is the live snapshot
(projected bytes above the budget left when every evictable resident is reclaimed),
and ``never_fit`` is asserted only against a fixed ``LOAD_GUARD_CEILING_GB`` — the
balanced ceiling follows host free memory, so only a fixed budget makes "never" a
claim about the model rather than the moment.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from portal.platform.inference.load_guard import OLLAMA
from portal.platform.inference.router.seat_fit import annotate, production_seats
from tests.unit.test_load_guard import GIB, OLLAMA_URL, Engines, guard


def _seat(seat_id: str, model: str, omlx_model: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"seat": seat_id, "model": model, "omlx_model": omlx_model, **extra}


async def test_seat_over_the_live_budget_is_flagged_but_not_never_fit() -> None:
    e = Engines(
        ollama={"router": GIB},  # pinned: stays beside every seat
        tags={"huge": 40 * GIB, "small": 2 * GIB},
        ceiling=20 * GIB,
    )
    report = await guard(e).seat_fit(
        OLLAMA_URL, [_seat("ws-huge", "huge"), _seat("ws-small", "small")]
    )
    # headroom 20, pinned router not evictable, margin 2 → 18 GiB for any seat.
    assert report["available_gib"] == pytest.approx(18)
    huge = next(r for r in report["seats"] if r["seat"] == "ws-huge")
    assert huge["ollama_projected_gib"] == pytest.approx(50)  # weights x factor
    assert huge["over_budget"] and huge["fits"] is False
    # the live ceiling follows host free memory, so "never" is not asserted from it
    assert not huge["never_fit"]
    assert report["never_fit"] == [] and report["over_budget"] == ["ws-huge"]
    assert "P5-OMLX-CEILING-001" in report["never_fit_basis"]
    assert report["ollama_residents"]["router"]["hold"] == "pinned"


async def test_protected_idle_counts_toward_the_fit_budget() -> None:
    e = Engines(ollama={"fallback": 10 * GIB}, tags={"m": 12 * GIB}, ceiling=10 * GIB)
    g = guard(e)
    g.protect(OLLAMA, "fallback", seconds=60)
    report = await g.seat_fit(OLLAMA_URL, [_seat("ws", "m")])
    # Protected idle yields before refusal, so its bytes are part of the budget:
    # 10 headroom + 10 idle - 2 margin = 18 >= 15 projected.
    assert report["idle_ollama_gib"] == pytest.approx(10)
    assert report["seats"][0]["fits"]


async def test_omlx_seat_fits_via_its_estimated_size() -> None:
    e = Engines(omlx={"native": {"size": 5 * GIB, "loaded": False}}, ceiling=20 * GIB)
    report = await guard(e).seat_fit(OLLAMA_URL, [_seat("ws", "gguf-tag", "native")])
    row = report["seats"][0]
    assert row["ollama_projected_gib"] is None  # the tag is not on Ollama
    assert row["omlx_projected_gib"] == pytest.approx(5)
    assert row["served"] and row["fits"] and not row["never_fit"]


async def test_resident_seat_fits_and_is_marked_resident() -> None:
    e = Engines(ollama={"m": 30 * GIB}, tags={"m": 30 * GIB}, ceiling=20 * GIB)
    report = await guard(e).seat_fit(OLLAMA_URL, [_seat("ws", "m")])
    row = report["seats"][0]
    assert row["resident"] and row["fits"] and not row["never_fit"]


async def test_unserved_seat_is_reported_not_flagged_never_fit() -> None:
    e = Engines(ceiling=20 * GIB)
    report = annotate(await guard(e).seat_fit(OLLAMA_URL, [_seat("ws", "ghost")]))
    row = report["seats"][0]
    assert not row["served"] and row["fits"] is None and not row["never_fit"]
    assert report["unserved"] == ["ws"]


async def test_undeclared_over_budget_is_cross_checked() -> None:
    e = Engines(tags={"huge": 40 * GIB}, ceiling=20 * GIB)
    seats = [
        _seat("ws-declared", "huge", stack_down_only=True),
        _seat("ws-undeclared", "huge", stack_down_only=False),
    ]
    report = annotate(await guard(e).seat_fit(OLLAMA_URL, seats))
    assert report["over_budget"] == ["ws-declared", "ws-undeclared"]
    assert report["undeclared_over_budget"] == ["ws-undeclared"]
    assert report["never_fit"] == [] and report["undeclared_never_fit"] == []


def test_production_seats_enumerates_bases_and_variants_not_bench() -> None:
    registry = SimpleNamespace(
        list_backends=lambda: [
            SimpleNamespace(type="omlx", resolve_model=lambda hint: f"native::{hint}")
        ]
    )
    seats = production_seats(registry)
    by_id = {s["seat"]: s for s in seats}
    assert "auto-reasoning" in by_id
    assert "auto-reasoning::math" in by_id
    assert by_id["auto-reasoning"]["omlx_model"] == f"native::{by_id['auto-reasoning']['model']}"
    assert not any(s["seat"].startswith("bench-") for s in seats)
    assert all(s["model"] for s in seats)


def test_seat_fit_route_is_registered() -> None:
    from portal.platform.inference.router_pipe import app

    assert any(getattr(r, "path", "") == "/admin/seat-fit" for r in app.routes)


async def test_working_set_fit_deduplicates_shared_model_and_flags_co_resident_over_budget() -> (
    None
):
    e = Engines(
        omlx={
            "Qwen3.8-27B-oQ4e-mtp": {"size": int(16.6 * GIB), "loaded": False},
            "Inkling-2-Mini-oQ4e-mtp": {"size": int(16.5 * GIB), "loaded": False},
            "gemma-4-26b-a4b-it-QAT-4bit": {"size": int(15.3 * GIB), "loaded": False},
        },
        ceiling=int(40 * GIB),
    )
    seats = [
        _seat("auto-compliance", "qwen-tag", "Qwen3.8-27B-oQ4e-mtp"),
        _seat("compliance-council-qwen38", "qwen-tag-32k", "Qwen3.8-27B-oQ4e-mtp"),
        _seat("security-reviewer", "inkling-tag", "Inkling-2-Mini-oQ4e-mtp"),
        _seat("hunt-reasoning", "gemma-tag", "gemma-4-26b-a4b-it-QAT-4bit"),
    ]
    working_sets = {
        "compliance-interactive": {
            "mode": "co_resident",
            "workspaces": ["auto-compliance", "compliance-council-qwen38"],
        },
        "hunt-forced": {
            "mode": "co_resident",
            "workspaces": ["security-reviewer", "hunt-reasoning"],
        },
        "security-hunt": {
            "mode": "yield",
            "workspaces": ["security-reviewer", "hunt-reasoning"],
        },
    }
    report = annotate(await guard(e).seat_fit(OLLAMA_URL, seats), working_sets=working_sets)
    by_ws = {row["working_set"]: row for row in report["working_sets"]}
    # Shared Qwen3.8 weights count once: 16.6 GiB <= 40 * 0.8 - 2 = 30.0 GiB.
    assert by_ws["compliance-interactive"]["projected_gib"] == pytest.approx(16.6, abs=0.1)
    assert by_ws["compliance-interactive"]["fits"] is True
    # Distinct 16.5 + 15.3 = 31.8 GiB > 30.0 GiB prefill-safe budget.
    assert by_ws["hunt-forced"]["projected_gib"] == pytest.approx(31.8, abs=0.1)
    assert by_ws["hunt-forced"]["fits"] is False
    assert by_ws["security-hunt"]["fits"] is False
    assert report["over_budget_working_sets"] == ["hunt-forced"]
