"""N-2: the Fara probe credits a call only when the reply carries it; a call found only in the
reasoning field is a template defect and is reported as one."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "tests" / "benchmarks"


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FARA_TAG", "fara-test")
    monkeypatch.syspath_prepend(str(BENCH))
    sys.modules.pop("bench_fara_cua_probe", None)
    return importlib.import_module("bench_fara_cua_probe")


def test_native_tool_calls_are_a_clean_source(probe) -> None:
    msg = {"tool_calls": [{"function": {"arguments": {"action": "click", "coordinate": [1, 2]}}}]}
    action, args, source = probe._extract_action(msg)
    assert (action, source) == ("click", "tool_calls")


def test_an_inline_call_in_content_is_content_sourced(probe) -> None:
    msg = {
        "content": '<tool_call>{"name":"computer_use","arguments":{"action":"click"}}</tool_call>'
    }
    action, _, source = probe._extract_action(msg)
    assert (action, source) == ("click", "content")


def test_an_inline_call_only_in_thinking_is_flagged(probe) -> None:
    msg = {
        "content": "",
        "thinking": '<tool_call>{"name":"computer_use","arguments":{"action":"click"}}</tool_call>',
    }
    action, _, source = probe._extract_action(msg)
    assert action == "click"
    assert source == "thinking"


def test_no_call_is_none(probe) -> None:
    assert probe._extract_action({"content": "I will click."}) == (None, {}, "none")
