"""Unit tests for tests/recall_scorer.py — deterministic, no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from recall_scorer import classify_lines, render_diff_ansi, score_function_recall


def _fn(text: str) -> str:
    return text.strip()


class TestExactReproduction:
    def test_exact_match(self):
        body = "def foo():\n    x = 1\n    y = 2\n    return x + y"
        result = score_function_recall(body, body, n_lines=4, pass_threshold=2)
        assert result["recall"] == 1.0
        assert result["passed"] is True
        assert result["missing"] == 0
        assert result["hallucinated"] == 0

    def test_full_recall_perfect(self):
        body = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj"
        result = score_function_recall(body, body, n_lines=10, pass_threshold=8)
        assert result["recall"] == 1.0
        assert result["passed"] is True
        assert result["matched"] == 10


class TestPartialRecall:
    def test_half_missing(self):
        expected = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10"
        produced = "line1\nline2\nline3\nline4\nline5"
        result = score_function_recall(expected, produced, n_lines=10, pass_threshold=4)
        assert result["recall"] == 0.5
        assert result["passed"] is True  # matched 5 >= threshold 4
        assert result["matched"] == 5
        assert result["missing"] == 5

    def test_below_threshold(self):
        expected = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj"
        produced = "a\nb"
        result = score_function_recall(expected, produced, n_lines=10, pass_threshold=4)
        assert result["recall"] == 0.2
        assert result["passed"] is False
        assert result["matched"] == 2
        assert result["missing"] == 8


class TestAllHallucinated:
    def test_all_hallucinated(self):
        expected = "a\nb\nc\nd"
        produced = "x\ny\nz"
        result = score_function_recall(expected, produced, n_lines=4, pass_threshold=2)
        assert result["recall"] == 0.0
        assert result["passed"] is False
        assert result["matched"] == 0
        assert result["hallucinated"] == 3

    def test_empty_produced(self):
        expected = "a\nb\nc\nd"
        result = score_function_recall(expected, "", n_lines=4, pass_threshold=2)
        assert result["recall"] == 0.0
        assert result["passed"] is False
        assert result["missing"] == 4


class TestBonusLines:
    def test_bonus_beyond_window(self):
        body = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj"
        expected = body
        produced = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk"
        result = score_function_recall(expected, produced, n_lines=10, pass_threshold=8)
        assert result["recall"] == 1.0
        assert result["bonus"] == 0
        assert result["hallucinated"] == 1

    def test_bonus_after_window_matches_later(self):
        expected = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk\nl"
        produced = "a\nb\nc\nd\ne\nf\ng\nh\ni\nj\nk"  # k is bonus
        result = score_function_recall(expected, produced, n_lines=10, pass_threshold=8)
        assert result["recall"] == 1.0
        assert result["bonus"] == 1


class TestClassifyAndRender:
    def test_classify_exact(self):
        body = "a\nb\nc"
        diff = classify_lines(body, body, n_lines=3)
        assert all(d["kind"] == "match" for d in diff)

    def test_classify_missing(self):
        expected = "a\nb\nc"
        produced = "a"
        diff = classify_lines(expected, produced, n_lines=3)
        kinds = [d["kind"] for d in diff]
        assert "match" in kinds
        assert "missing" in kinds

    def test_render_diff_ansi(self):
        body = "a\nb\nc"
        diff = classify_lines(body, body, n_lines=3)
        rendered = render_diff_ansi(diff)
        assert "match" in rendered
        assert "\033" in rendered


class TestShortFunction:
    def test_short_function_denominator(self):
        expected = "a\nb\nc"
        produced = "a\nb\nc"
        result = score_function_recall(expected, produced, n_lines=20, pass_threshold=2)
        assert result["recall"] == 1.0
        assert result["expected_lines"] == 3  # min(20, 3)


class TestLeadingTrailingBlankLines:
    def test_blank_lines_stripped(self):
        expected = "\n\na\nb\nc\n\n"
        produced = "a\nb\nc"
        result = score_function_recall(expected, produced, n_lines=4, pass_threshold=2)
        assert result["recall"] == 1.0
