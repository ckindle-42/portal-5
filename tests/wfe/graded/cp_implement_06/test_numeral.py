"""Hidden graded suite for code-implement-06. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import numeral as mod
import pytest

CASES = [
    ("result = numeral_value('XIV')", 14),
    ("result = numeral_value('MCMXCIV')", 1994),
    ("result = numeral_value('III')", 3),
    ("result = numeral_value('IIII')", ("__raises__", "ValueError")),
    ("result = numeral_value('')", ("__raises__", "ValueError")),
    ("result = numeral_value('iv')", ("__raises__", "ValueError")),
    ("result = numeral_value('VX')", ("__raises__", "ValueError")),
    ("result = numeral_value('IC')", ("__raises__", "ValueError")),
    ("result = numeral_value('MMMCMXCIX')", 3999),
    ("result = numeral_value('MMMM')", ("__raises__", "ValueError")),
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
