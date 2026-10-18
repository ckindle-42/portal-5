"""Offline checks for production smoke's empty-KB grading (finding F)."""

from __future__ import annotations

import importlib

smoke = importlib.import_module("scripts.wfe_production_smoke")


def test_kb_search_cases_expect_the_empty_production_kb() -> None:
    by_tool = {c.tool: c for c in smoke.CASES}
    assert by_tool["kb_search"].expect_empty_kb
    assert by_tool["kb_search_all"].expect_empty_kb
    assert not by_tool["kb_list"].expect_empty_kb


def _case(tool: str) -> smoke.Case:
    return next(c for c in smoke.CASES if c.tool == tool)


def _patch_turn(monkeypatch, spans: list[dict], answer: str = "No knowledge base has content."):
    monkeypatch.setattr(
        smoke,
        "owui",
        lambda path, body: {
            "choices": [{"message": {"content": answer}}],
            "usage": {"prompt_tokens": 12},
        },
    )
    monkeypatch.setattr(smoke, "newest_trace", lambda ws, since: {"spans": spans})


def test_kb_row_accepted_when_model_lists_the_empty_store(monkeypatch) -> None:
    _patch_turn(
        monkeypatch,
        [
            {"name": "tool.requested", "tool": "kb_list"},
            {"name": "tool.completed", "tool": "kb_list", "outcome": "ok"},
        ],
    )

    r = smoke.run_case("auto-research", _case("kb_search"))

    assert r.called is False
    assert r.accepted is True
    assert "no KB has content" in r.note
    assert smoke.needs_look(r) is False


def test_kb_row_still_flagged_when_kb_list_failed(monkeypatch) -> None:
    _patch_turn(
        monkeypatch,
        [
            {"name": "tool.requested", "tool": "kb_list"},
            {"name": "tool.completed", "tool": "kb_list", "outcome": "error"},
        ],
    )

    r = smoke.run_case("auto-research", _case("kb_search"))

    assert r.accepted is False
    assert smoke.needs_look(r) is True


def test_kb_row_still_flagged_when_no_kb_tool_was_called(monkeypatch) -> None:
    _patch_turn(monkeypatch, [])

    r = smoke.run_case("auto-research", _case("kb_search"))

    assert r.accepted is False
    assert smoke.needs_look(r) is True


def test_kb_row_still_flagged_when_answer_is_a_refusal(monkeypatch) -> None:
    _patch_turn(
        monkeypatch,
        [
            {"name": "tool.requested", "tool": "kb_list"},
            {"name": "tool.completed", "tool": "kb_list", "outcome": "ok"},
        ],
        answer="I can't search knowledge bases.",
    )

    r = smoke.run_case("auto-research", _case("kb_search"))

    assert r.accepted is True
    assert smoke.needs_look(r) is True
