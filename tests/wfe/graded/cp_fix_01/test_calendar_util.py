"""Hidden graded suite for code-fix-01. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import calendar_util as mod
import pytest

CASES = [
    ("result = is_leap_year(2024)", True),
    ("result = is_leap_year(1900)", False),
    ("result = is_leap_year(2000)", True),
    ("result = is_leap_year(2100)", False),
    ("result = is_leap_year(1600)", True),
    ("result = is_leap_year(1999)", False),
    ("result = is_leap_year(2400)", True),
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
