"""Offline checks for production smoke's empty-KB grading (finding F)."""

from __future__ import annotations

import importlib

smoke = importlib.import_module("scripts.wfe_production_smoke")


def test_kb_search_cases_expect_the_empty_production_kb() -> None:
    by_tool = {c.tool: c for c in smoke.CASES}
    assert by_tool["kb_search"].expect_empty_kb
    assert by_tool["kb_search_all"].expect_empty_kb
    assert not by_tool["kb_list"].expect_empty_kb
