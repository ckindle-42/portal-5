"""Positional recall scorer — LCS line-alignment under long context.

Method adapted from github.com/alexziskind1/codeneedle (Alex Ziskind).
Scores verbatim function-body reproduction by longest-common-subsequence
line alignment, reporting matched / missing / hallucinated / bonus lines,
per-function pass/fail, and a per-line classification for rendering.

Pure stdlib — no external dependencies. Designed to be unit-tested
deterministically without any LLM involved.
"""

from __future__ import annotations

import difflib
from typing import Any


def _normalize_lines(text: str) -> list[str]:
    """Strip trailing whitespace, drop leading/trailing blank lines."""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _lcs_match(expected: list[str], produced: list[str]):
    """Run difflib SequenceMatcher over line lists. Returns opcodes."""
    return difflib.SequenceMatcher(None, expected, produced).get_opcodes()


def score_function_recall(
    expected: str,
    produced: str,
    n_lines: int = 20,
    pass_threshold: int = 8,
) -> dict[str, Any]:
    """Score one function-body reproduction by LCS line alignment.

    Compares the first *n_lines* of *expected* against *produced*.
    Returns a dict with matched / missing / hallucinated / bonus counts,
    recall ratio, pass/fail, and per-line diff classification.
    """
    exp_lines = _normalize_lines(expected)
    prod_lines = _normalize_lines(produced)

    window = exp_lines[:n_lines]
    beyond = exp_lines[n_lines:]

    opcodes = _lcs_match(window, prod_lines)

    matched = 0
    missing = 0
    hallucinated = 0
    bonus = 0

    # Track which prod lines are accounted for (matched or bonus)
    prod_accounted: set[int] = set()

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            matched += i2 - i1
            prod_accounted.update(range(j1, j2))
        elif tag == "delete":
            missing += i2 - i1
        elif tag == "replace":
            missing += i2 - i1
            # The replace insert lines are hallucinated (not in expected)
            hallucinated += j2 - j1
            prod_accounted.update(range(j1, j2))
        elif tag == "insert":
            hallucinated += j2 - j1
            prod_accounted.update(range(j1, j2))

    # Check if any produced lines beyond the matched/hallucinated window
    # match lines from the "beyond" portion of expected. Also reclassify
    # insert/replace lines — if an inserted line matches a beyond-window
    # expected line, it's bonus, not hallucinated.
    for j, pline in enumerate(prod_lines):
        # Check if this line appears in the beyond-window expected lines
        for bline in beyond:
            if pline == bline:
                bonus += 1
                if j in prod_accounted:
                    hallucinated = max(0, hallucinated - 1)
                break

    denominator = min(n_lines, len(exp_lines))
    recall = matched / denominator if denominator > 0 else 0.0
    passed = matched >= pass_threshold

    diff = classify_lines(expected, produced, n_lines)

    return {
        "matched": matched,
        "missing": missing,
        "hallucinated": hallucinated,
        "bonus": bonus,
        "expected_lines": denominator,
        "recall": round(recall, 4),
        "passed": passed,
        "diff": diff,
    }


def classify_lines(
    expected: str,
    produced: str,
    n_lines: int = 20,
) -> list[dict[str, Any]]:
    """Return per-line classification for rendering a color diff.

    Each entry: {"line": str, "kind": "match"|"missing"|"hallucinated"|"bonus"}
    """
    exp_lines = _normalize_lines(expected)
    prod_lines = _normalize_lines(produced)
    window = exp_lines[:n_lines]

    opcodes = _lcs_match(window, prod_lines)
    result: list[dict[str, Any]] = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            for i in range(i1, i2):
                result.append({"line": window[i], "kind": "match"})
        elif tag == "delete":
            for i in range(i1, i2):
                result.append({"line": window[i], "kind": "missing"})
        elif tag == "replace":
            for i in range(i1, i2):
                result.append({"line": window[i], "kind": "missing"})
            for j in range(j1, j2):
                result.append({"line": prod_lines[j], "kind": "hallucinated"})
        elif tag == "insert":
            for j in range(j1, j2):
                result.append({"line": prod_lines[j], "kind": "hallucinated"})

    # Lines in produced past what was aligned, check for bonus
    max_aligned_j = max((j2 for _, _, _, _, j2 in opcodes), default=0)
    beyond = exp_lines[n_lines:]
    for j in range(max_aligned_j, len(prod_lines)):
        pline = prod_lines[j]
        kind = "hallucinated"
        for bline in beyond:
            if pline == bline:
                kind = "bonus"
                break
        result.append({"line": pline, "kind": kind})

    return result


_COLORS = {
    "match": "\033[90m",  # gray
    "missing": "\033[38;5;214m",  # orange
    "hallucinated": "\033[33m",  # yellow
    "bonus": "\033[36m",  # cyan
}
_RESET = "\033[0m"


def render_diff_ansi(diff: list[dict[str, Any]]) -> str:
    """Render a classified line list as ANSI-color output, codeneedle style."""
    out: list[str] = []
    for entry in diff:
        kind = entry["kind"]
        color = _COLORS.get(kind, "")
        out.append(f"  {color}{entry['line']}{_RESET}  [{kind}]")
    return "\n".join(out)
