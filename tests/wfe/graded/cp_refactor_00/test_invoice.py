"""Hidden graded suite for code-refactor-00. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import invoice as mod
import pytest

CASES = [
    ("result = total([(250, 2), (100, 3)], 10, 5)", 836),
    ("result = total([], 20, 0)", 0),
    ("result = total([(999, 1)], 0, 100)", 0),
    ("result = subtotal([(250, 2), (100, 3)])", 800),
    ("result = subtotal([])", 0),
    ("result = subtotal([(7, 0), (3, 3)])", 9),
    ("result = total([(1000, 2)], 7, 15)", 1819),
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
