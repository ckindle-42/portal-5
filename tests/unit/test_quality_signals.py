"""Unit tests for quality_signals V11 verifier upgrades.

Proves the fix: correct-but-differently-worded coding now scores high,
and keyword-stuffed-but-wrong coding scores low. The contrast IS the fix.
"""

from __future__ import annotations

# ── Test: keyword-only quality_score (original behavior, no verifier) ─────────


def test_general_still_uses_keyword_coverage():
    """General category has no verifier — must still use keyword matching."""
    from tests.quality_signals import quality_score

    text = "physical data link network transport session presentation application"
    score = quality_score("general", text)
    assert score == 1.0


def test_general_partial_match():
    from tests.quality_signals import quality_score

    text = "physical network transport"
    score = quality_score("general", text)
    assert 0.4 <= score <= 0.6


# ── Test: coding verifier — correct code scores high, keyword-stuffed wrong scores low ──


def test_coding_verifier_correct_code_scores_high():
    """A correct merge_intervals implementation must score 1.0 regardless of wording."""
    from tests.quality_signals import quality_score

    correct_code = """```python
def merge_intervals(intervals):
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    result = [intervals[0]]
    for curr in intervals[1:]:
        last = result[-1]
        if curr[0] <= last[1]:
            last[1] = max(last[1], curr[1])
        else:
            result.append(curr)
    return result
```"""
    score = quality_score("coding", correct_code)
    assert score == 1.0, f"Expected 1.0 for correct code, got {score}"


def test_coding_verifier_different_wording_scores_high():
    """A differently-worded but correct implementation must still score high."""
    from tests.quality_signals import quality_score

    # Uses different variable names but correct algorithm
    different_code = """```python
def merge_intervals(items):
    # Sort by start time and merge overlapping ranges
    if not items:
        return []
    items.sort()
    out = [items[0]]
    for s, e in items[1:]:
        prev_s, prev_e = out[-1]
        if s <= prev_e:
            out[-1] = [prev_s, max(prev_e, e)]
        else:
            out.append([s, e])
    return out
```"""
    score = quality_score("coding", different_code)
    assert score == 1.0, f"Expected 1.0 for differently-worded correct code, got {score}"


def test_coding_verifier_keyword_stuffed_wrong_scores_low():
    """An answer with all the right keywords but wrong logic must score 0."""
    from tests.quality_signals import quality_score

    wrong_code = """```python
def merge_intervals(intervals):
    # Got all the right keywords but wrong logic!
    lst = list(intervals)
    tup = tuple(lst)
    lst.sort()
    merged = []
    for i in lst:
        if not merged or i[0] > merged[-1][1]:
            merged.append(i)
    # overlapping is never handled — always skip merging
    return merged
```"""
    score = quality_score("coding", wrong_code)
    assert score == 0.0, f"Expected 0.0 for wrong code, got {score}"


def test_coding_verifier_no_code_block_scores_zero():
    """No fenced code block means the verifier can't run — score 0."""
    from tests.quality_signals import quality_score

    text = "Here is the answer: def merge_intervals(intervals): list tuple sort merged overlap"
    score = quality_score("coding", text)
    assert score == 0.0


# ── Test: reasoning verifier — checks numeric, not keywords ──────────────────


def test_reasoning_verifier_correct_answer_scores_high():
    """A reasoning answer with the correct numbers must score high."""
    from tests.quality_signals import quality_score

    # Correct answer: bottleneck is beds, capacity ~2.29/hr
    answer = (
        "The bottleneck is the 8 beds. With an average stay of 3.5 hours, "
        "the hospital can discharge 8/3.5 = 2.29 patients per hour. "
        "Since arrivals are 30/hr, the queue grows at 27.71/hr. "
        "Average wait time exceeds 700 minutes."
    )
    score = quality_score("reasoning", answer)
    assert score >= 0.67, f"Expected >=0.67, got {score}"


def test_reasoning_verifier_keyword_stuffed_wrong_scores_low():
    """An answer with keywords but wrong numeric conclusion scores low."""
    from tests.quality_signals import quality_score

    # Uses all the right words but completely wrong math
    answer = (
        "The bottleneck is the doctors. The nurse capacity is higher. "
        "With 8 beds the wait time is minimal, about 5 minutes. "
        "The arrival rate of 30 per hour is well within capacity."
    )
    score = quality_score("reasoning", answer)
    assert score < 0.67, f"Expected <0.67 for wrong answer, got {score}"


# ── Test: verifier fallback ──────────────────────────────────────────────────


def test_coding_falls_back_to_keyword_when_verifier_unavailable(monkeypatch):
    """When capability_lib import fails, coding must fall back to keyword."""
    from tests import quality_signals as qs

    # Make _verify_coding return the sentinel -1.0 to trigger keyword fallback
    monkeypatch.setitem(qs._VERIFIERS, "coding", lambda _r: -1.0)

    text = "def merge_intervals list tuple intervals.sort merged overlap"
    score = qs.quality_score("coding", text)
    # Should use keyword matching: all 6 signals found
    assert score == 1.0

    # Restore the original verifier
    monkeypatch.undo()
