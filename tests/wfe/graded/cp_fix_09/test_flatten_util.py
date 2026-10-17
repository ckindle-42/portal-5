"""Hidden graded suite for code-fix-09. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import flatten_util as mod
import pytest

CASES = [
    ("result = flatten([1, [2, [3, [4]]]])", [1, 2, 3, 4]),
    ("result = flatten([[1], [2]])", [1, 2]),
    ("result = flatten([])", []),
    ("result = flatten([[], [[]]])", []),
    ("result = flatten(['ab', ['cd', ['ef']]])", ["ab", "cd", "ef"]),
    ("result = flatten([1, [2, 3], 4])", [1, 2, 3, 4]),
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
