"""Hidden graded suite for code-fix-03. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pager as mod
import pytest

CASES = [
    ("result = paginate([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 1, 3)", [0, 1, 2]),
    ("result = paginate([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 2, 3)", [3, 4, 5]),
    ("result = paginate([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 4, 3)", [9]),
    ("result = paginate([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 5, 3)", []),
    ("result = paginate([], 1, 3)", []),
    ("result = paginate(['a', 'b', 'c', 'd', 'e'], 3, 2)", ["e"]),
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
