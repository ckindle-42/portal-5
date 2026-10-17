"""Hidden graded suite for code-implement-08. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import budget as mod
import pytest

CASES = [
    ("result = split_by_budget([], 5)", []),
    ("result = split_by_budget([1, 2, 3, 4, 5], 6)", [[1, 2, 3], [4], [5]]),
    ("result = split_by_budget([9, 1], 5)", [[9], [1]]),
    ("result = split_by_budget([5, 5, 5], 5)", [[5], [5], [5]]),
    ("result = split_by_budget([2, 2, 2, 2], 4)", [[2, 2], [2, 2]]),
    ("result = split_by_budget([1], 1)", [[1]]),
]


@pytest.mark.parametrize("code,expected", CASES)
def test_case(code, expected):
    ns = dict(vars(mod))
    if isinstance(expected, tuple) and expected[:1] == ("__raises__",):
        with pytest.raises(getattr(builtins, expected[1])):
            exec(code, ns)
    else:
        exec(code, ns)
        assert ns["result"] == expected
