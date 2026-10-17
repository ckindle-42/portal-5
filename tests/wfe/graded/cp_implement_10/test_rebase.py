"""Hidden graded suite for code-implement-10. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import rebase as mod

CASES = [
    ("result = convert_digits('ff', 16, 2)", "11111111"),
    ("result = convert_digits('0', 10, 2)", "0"),
    ("result = convert_digits('zz', 36, 10)", "1295"),
    ("result = convert_digits('101', 2, 8)", "5"),
    ("result = convert_digits('12', 2, 10)", ("__raises__", "ValueError")),
    ("result = convert_digits('', 10, 2)", ("__raises__", "ValueError")),
    ("result = convert_digits('9', 10, 37)", ("__raises__", "ValueError")),
    ("result = convert_digits('00ff', 16, 10)", "255"),
    ("result = convert_digits('1010', 2, 16)", "A"),
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
