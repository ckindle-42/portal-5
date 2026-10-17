"""Hidden graded suite for code-fix-04. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import growth as mod
import pytest

CASES = [
    ("result = percent_change(3, 4)", 33.3),
    ("result = percent_change(200, 250)", 25.0),
    ("result = percent_change(0, 5)", None),
    ("result = percent_change(80, 60)", -25.0),
    ("result = percent_change(7, 7)", 0.0),
    ("result = percent_change(1000, 1)", -99.9),
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
