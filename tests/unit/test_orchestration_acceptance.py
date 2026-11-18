"""Tests for orchestration_acceptance.py against the fake Pipeline rig."""

from __future__ import annotations

import orchestration_acceptance as acceptance  # noqa: E402
import pytest


@pytest.mark.parametrize(
    ("receipt", "expected"),
    [
        ({"results": [{"status": "PASS"}]}, 0),
        ({"results": [{"status": "FAIL"}]}, 1),
        ({"results": [{"status": "SKIP", "required": True}]}, 1),
        ({"results": [{"status": "SKIP", "required": False}]}, 0),
        ({"results": [], "blocked": "WFE active"}, 3),
        ({"results": [], "interrupted": True}, 130),
        ({"results": [{"status": "PASS"}], "aborted": "WFE started"}, 1),
    ],
)
def test_exit_code_never_treats_required_skips_as_success(receipt: dict, expected: int):
    assert acceptance._exit_code(receipt) == expected
