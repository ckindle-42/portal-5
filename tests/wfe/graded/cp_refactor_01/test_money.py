"""Hidden graded suite for code-refactor-01. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import money as mod
import pytest

CASES = [
    ("result = fmt_money(1234)", "$12.34"),
    ("result = fmt_money(-5)", "-$0.05"),
    ("result = fmt_money(0)", "$0.00"),
    ("result = format_cents(1234)", "$12.34"),
    ("result = format_cents(-5)", "-$0.05"),
    ("result = format_cents(100)", "$1.00"),
    ("result = fmt_money(99999) == format_cents(99999)", True),
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
