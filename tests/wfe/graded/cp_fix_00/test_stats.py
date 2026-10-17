"""Hidden graded suite for code-fix-00. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import stats as mod

CASES = [
    ("result = mean_of_top([1, 5, 3, 9], 2)", 7.0),
    ("result = mean_of_top([4, 8], 1)", 8.0),
    ("result = mean_of_top([], 3)", 0.0),
    ("result = mean_of_top([2, 2, 2], 2)", 2.0),
    ("result = mean_of_top([10, 0, 5, 7], 3)", 7.333333333333333),
    ("result = mean_of_top([6], 4)", 6.0),
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
