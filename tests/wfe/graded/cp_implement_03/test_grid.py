"""Hidden graded suite for code-implement-03. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import grid as mod
import pytest

CASES = [
    ("result = spin_grid([])", []),
    ("result = spin_grid([[1, 2, 3], [4, 5, 6]])", [[4, 1], [5, 2], [6, 3]]),
    ("result = spin_grid([[1]])", [[1]]),
    ("result = spin_grid([[1, 2], [3, 4], [5, 6]])", [[5, 3, 1], [6, 4, 2]]),
    ("result = spin_grid([['a', 'b']])", [["a"], ["b"]]),
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
