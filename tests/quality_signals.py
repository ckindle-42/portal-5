"""Per-category quality signal definitions.

Used by both bench_tps and the UAT driver to score response quality
beyond raw TPS or keyword presence. A response gets quality_score in
[0.0, 1.0] = (signals_found / signals_expected).

Signals are tuned to the prompt library in tests/benchmarks/bench_tps.py
PROMPTS dict. If you change a category's prompt, update its signals here.

A signal may be a string (exact substring match) or a tuple of strings
(OR group: any one match counts as one signal hit).

V11 (2026-06-30): Optional per-category verifiers. If a category defines a
``verifier`` callable (function taking response_text → 0..1 score),
quality_score prefers it over keyword matching. Falls back to signal counting
when no verifier exists. Two categories upgraded:

- coding: runs merge_intervals through capability_lib.run_python_against_tests
- reasoning: checks the numeric ER bottleneck answer (keyword as fallback)
"""

from __future__ import annotations

import re
from collections.abc import Callable

# ── Verifier callables (optional per-category) ───────────────────────────────


def _verify_coding(response: str) -> float:
    """Run the coding answer against merge_intervals unit tests."""
    try:
        from tests.benchmarks.capability_lib import (
            extract_code_block,
            run_python_against_tests,
        )
    except ImportError:
        return -1.0  # signal: unavailable, fall back to keyword

    code = extract_code_block(response, "python")
    if not code:
        return 0.0

    test = (
        "from solution import merge_intervals\n\n"
        "def test_basic():\n"
        "    assert merge_intervals([[1,3],[2,6],[8,10]]) == [[1,6],[8,10]]\n\n"
        "def test_single():\n"
        "    assert merge_intervals([[1,4]]) == [[1,4]]\n\n"
        "def test_non_overlapping():\n"
        "    assert merge_intervals([[1,2],[3,4],[5,6]]) == [[1,2],[3,4],[5,6]]\n"
    )
    passed, _ = run_python_against_tests(code, test)
    return 1.0 if passed else 0.0


def _verify_reasoning(response: str) -> float:
    """Check the ER bottleneck numeric answer instead of keyword bingo.

    The correct ER bottleneck answer involves:
    - 30 patients/hr arrival rate
    - 8 beds with avg 3.5 hr stay → capacity of 8/(3.5) ≈ 2.29 patients/hr exit
    - Bottleneck is the beds (doctors 12 patients/hr, nurses 16 patients/hr)
    - Wait time ≈ 12+ hrs or 700+ minutes
    """
    try:
        from tests.benchmarks.capability_lib import extract_final_answer
    except ImportError:
        return -1.0

    final = extract_final_answer(response).lower()

    # Check for the correct numeric answer (bottleneck is beds, ~2.29/hr)
    correct_signals = [
        bool(re.search(r"2\.2[0-9]|2\.3[0-9]", final)),  # beds capacity ~2.29/hr
        "bottleneck" in final or "bottleneck" in final,
        "bed" in final or "beds" in final,
    ]
    return sum(correct_signals) / len(correct_signals)


_VERIFIERS: dict[str, Callable[[str], float]] = {
    "coding": _verify_coding,
    "reasoning": _verify_reasoning,
}

QUALITY_SIGNALS: dict[str, list] = {
    "general": [
        # Prompt asks for OSI 7 layers with protocol examples
        "physical",
        "data link",
        "network",
        "transport",
        "session",
        "presentation",
        "application",
    ],
    "coding": [
        # Prompt asks for merge_intervals function
        "def merge_intervals",
        "list",
        "tuple",
        "intervals.sort",
        "merged",
        "overlap",
    ],
    "security": [
        # Prompt asks for SSH brute-force MITRE ATT&CK analysis
        "T1110",
        "MITRE",
        "ATT&CK",
        "containment",
        "detection",
        "block",
    ],
    "reasoning": [
        # Prompt asks for ER bottleneck analysis.
        # Tuple = OR group: any one term counts as one hit.
        # auto-compliance uses formal math notation ("capacity" instead of
        # "bottleneck", fractional hours instead of "minute").
        ("bottleneck", "capacity"),
        "doctor",
        "nurse",
        "bed",
        ("wait", "arrival"),
        ("minute", "hour"),
    ],
    "creative": [
        # Prompt asks for noir detective opening, memory-as-currency
        "memory",
        "detective",
        "city",
        "rain",
    ],
    "vision": [
        # Prompt is meta — describe the analysis framework
        "objects",
        "text",
        "scene",
        "anomalies",
        "confidence",
    ],
    "math": [
        # Prompt: train meeting (answer: 11:00 AM, 180 km from X),
        # combinatorics team (answer: 50), quadratic (answer: n=3, n=-6)
        "180",  # km from Station X — correct train meeting distance
        "11",  # 11:00 AM meeting time
        "50",  # correct combinatorics answer: C(5,2)*C(4,1) + C(5,3)*C(4,0) = 50
        "factor",  # factoring the quadratic n²+3n-18
        "-6",  # correct root of quadratic
        "n = 3",  # other root (with space — avoids false match on "n=3" inside words)
    ],
}


def quality_score(category: str, response_text: str) -> float:
    """Return a quality score in [0.0, 1.0] for the given category and response.

    If the category has an optional verifier (V11), it is preferred and
    keyword matching is used as fallback when the verifier is unavailable
    or returns a negative sentinel. Otherwise, signals are matched
    case-insensitively. Score is signals-found / signals-expected.
    A signal may be a string (single keyword) or a tuple (OR group: any one
    hit counts). Categories without defined signals return 1.0.
    """
    verifier = _VERIFIERS.get(category)
    if verifier is not None:
        try:
            v_score = verifier(response_text)
            if v_score >= 0.0:  # -1.0 = verifier unavailable, fall through
                return v_score
        except Exception:
            pass  # verifier failed — fall back to keyword

    signals = QUALITY_SIGNALS.get(category, [])
    if not signals:
        return 1.0
    response_lower = response_text.lower()
    found = 0
    for sig in signals:
        if isinstance(sig, tuple):
            found += any(s.lower() in response_lower for s in sig)
        else:
            found += sig.lower() in response_lower
    return found / len(signals)
