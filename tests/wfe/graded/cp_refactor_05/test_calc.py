"""Hidden graded suite for code-refactor-05. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import calc as mod
import pytest

CASES = [
    ('result = apply("add", 2, 3)', 5),
    ('result = apply("div", 9, 2)', 4.5),
    ('result = apply("mul", 4, 5)', 20),
    ("result = sorted(OPERATIONS)", ["add", "div", "mul", "sub"]),
    ("result = OPERATIONS['sub'](10, 4)", 6),
    ('result = apply("sub", 1, 5)', -4),
    ('result = apply("pow", 2, 3)', ("__raises__", "ValueError")),
    ('result = apply("div", 1, 0)', ("__raises__", "ZeroDivisionError")),
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
