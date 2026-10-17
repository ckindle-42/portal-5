"""Hidden graded suite for code-fix-08. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import due as mod
import pytest

CASES = [
    ("result = due_in_days('2031-03-10', '2031-03-15')", 5),
    ("result = due_in_days('2031-03-10', '2031-03-10')", 0),
    ("result = due_in_days('2031-02-27', '2031-03-02')", 3),
    ("result = due_in_days('2031-12-30', '2032-01-02')", 3),
    ("result = due_in_days('2031-05-20', '2031-05-01')", -19),
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
