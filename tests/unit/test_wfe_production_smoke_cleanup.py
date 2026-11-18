"""Offline checks for production smoke's memory-note cleanup."""

from __future__ import annotations

import importlib

smoke = importlib.import_module("scripts.wfe_production_smoke")


def test_remember_result_id_is_captured_from_answer_text() -> None:
    memory_id = "16c30fcb-7b52-4677-9141-9a0a5277b23d"
    assert smoke._memory_id_from_tool_result_text(f"Stored memory id: {memory_id}") == memory_id
    assert smoke._memory_id_from_tool_result_text("Stored, but no id was included") == ""
