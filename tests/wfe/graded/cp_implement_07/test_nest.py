"""Hidden graded suite for code-implement-07. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import nest as mod
import pytest

CASES = [
    ("result = nests_ok('')", True),
    ("result = nests_ok('([]{})')", True),
    ("result = nests_ok('([)]')", False),
    ("result = nests_ok('((')", False),
    ("result = nests_ok('a(b)c]')", False),
    ("result = nests_ok('{[()]}x')", True),
    ("result = nests_ok(')(')", False),
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
