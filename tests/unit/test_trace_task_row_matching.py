"""Trace matching by workspace + recency must never pick an OWUI task call.

OWUI's title/tag/follow-up generation arrives as an ordinary chat turn on the same
workspace seconds after the graded one (context_inject._is_owui_task_prompt), so a
summary matched only on identity + recency can return the task call's trace. The
producer marks such turns (owui_task) and both time-based matchers skip them; the
summary also carries `requested`, which both matchers include in their identity set.
"""

from __future__ import annotations

import importlib

prodpath = importlib.import_module("scripts.prodpath")
owui_client = importlib.import_module("tests.qat.owui_client")

TURN = {
    "correlation_id": "p5-turn",
    "workspace": "auto-security",
    "started_at": 100.0,
}
TASK = {
    "correlation_id": "p5-task",
    "workspace": "auto-security",
    "started_at": 200.0,
    "owui_task": True,
}


def test_prodpath_select_trace_skips_the_owui_task_row() -> None:
    target = prodpath.SeatTarget("auto-security", None, "m")
    trace = prodpath.select_trace([TASK, TURN], target, 50.0)
    assert trace["correlation_id"] == "p5-turn"


def test_prodpath_select_trace_still_skips_unrelated_workspaces() -> None:
    target = prodpath.SeatTarget("auto-security", None, "m")
    other = {"correlation_id": "p5-x", "workspace": "other", "started_at": 200.0}
    assert prodpath.select_trace([other], target, 50.0) is None


def test_qat_row_matcher_skips_the_owui_task_row() -> None:
    match = owui_client._trace_row_matches
    assert match(TASK, {"auto-security"}, 50.0) is False
    assert match(TURN, {"auto-security"}, 50.0) is True
    assert match({"workspace": "other", "started_at": 100.0}, {"auto-security"}, 50.0) is False


def test_identity_match_prefers_the_served_turn_over_a_newer_refusal() -> None:
    """s2-p1-auto: the guard row has workspace ``auto`` and no model, so newest-wins
    bound it and the served trace (requested ``auto``, model set) was missed."""
    started = 1_700_000_000.0
    refusal = {
        "correlation_id": "p5-refusal",
        "workspace": "auto",
        "requested": None,
        "model": None,
        "outcome": "safety_refusal",
        "started_at": started + 2,
    }
    served = {
        "correlation_id": "p5-served",
        "workspace": "auto-general-uncensored",
        "requested": "auto",
        "model": "Inkling-2-Mini-abliterated-oQ4e-mtp",
        "outcome": "complete",
        "started_at": started,
    }
    chosen = owui_client._trace_candidates([refusal, served], None, {"auto"}, started)
    assert [row["correlation_id"] for row in chosen] == ["p5-served"]
    lone = owui_client._trace_candidates([refusal], None, {"auto"}, started)
    assert [row["correlation_id"] for row in lone] == ["p5-refusal"]
