"""Thin capability_lib scoring wrapper, isolated so runner.py can monkeypatch it cleanly."""

from __future__ import annotations

from tests.benchmarks.capability_lib import (
    extract_code_block,
    run_python_against_tests,
)


def score_code(response: str, hidden_tests: str, *, timeout: int = 20) -> tuple[bool, str, str]:
    """Returns (passed, pytest_output[-1500:], extracted_code)."""
    code = extract_code_block(response, "python")
    if not code:
        return False, "NO_CODE_BLOCK: model response contained no ```python fenced block", ""
    passed, output = run_python_against_tests(code, hidden_tests, timeout=timeout)
    return passed, output[-1500:], code
