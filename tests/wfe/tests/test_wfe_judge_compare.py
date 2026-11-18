"""Tests for tests/wfe/judge_compare.py — all mock, no network."""

from __future__ import annotations

from tests.wfe import judge_compare as compare


class TestKappa:
    def test_no_data_returns_none(self):
        assert compare._kappa([]) is None

    def test_perfect_agreement_is_one(self):
        pairs = [("A", "A"), ("B", "B"), ("A", "A")]
        k = compare._kappa(pairs)
        assert k is not None
        assert abs(k - 1.0) < 1e-9

    def test_chance_agreement_gives_negative_kappa(self):
        # All pairs are cross — max disagreement.
        pairs = [("A", "B"), ("B", "A"), ("A", "B"), ("B", "A")]
        k = compare._kappa(pairs)
        assert k is not None
        assert k < 0
