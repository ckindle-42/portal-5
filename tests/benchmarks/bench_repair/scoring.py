"""Thin wrapper over capability_lib for scoring.

Kept as a separate module so runner.py has one import surface for grading
and can be monkey-patched cleanly in unit tests.
"""

from __future__ import annotations

from tests.benchmarks.capability_lib import (
    extract_code_block,
    run_python_against_tests,
)


def score_code(response: str, hidden_tests: str, *, timeout: int = 20) -> tuple[bool, str, str]:
    """Extract code from a model response and run hidden tests against it.

    Returns (passed, pytest_output, extracted_code).
    - passed: True iff pytest exit 0
    - pytest_output: last 1500 chars of pytest stdout+stderr (for repair prompt)
    - extracted_code: the code block extracted from response (empty if none)
    """
    code = extract_code_block(response, "python")
    if not code:
        return False, "NO_CODE_BLOCK: model response contained no ```python fenced block", ""
    passed, output = run_python_against_tests(code, hidden_tests, timeout=timeout)
    return passed, output[-1500:], code
