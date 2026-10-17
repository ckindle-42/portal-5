"""Hidden graded suite for code-implement-01. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import spans as mod

CASES = [
    ("result = join_spans([])", []),
    ("result = join_spans([(1, 3), (2, 6), (8, 10), (15, 18)])", [(1, 6), (8, 10), (15, 18)]),
    ("result = join_spans([(1, 4), (5, 6)])", [(1, 6)]),
    ("result = join_spans([(5, 5), (1, 2), (3, 3)])", [(1, 3), (5, 5)]),
    ("result = join_spans([(1, 10), (2, 3)])", [(1, 10)]),
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
