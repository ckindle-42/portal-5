"""Hidden graded suite for code-implement-11. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import paths as mod
import pytest

CASES = [
    ("result = tidy_path('/a/b/../c//d/.')", "/a/c/d"),
    ("result = tidy_path('a/./b/..')", "a"),
    ("result = tidy_path('../../x')", "../../x"),
    ("result = tidy_path('/..')", "/"),
    ("result = tidy_path('')", "."),
    ("result = tidy_path('a/../..')", ".."),
    ("result = tidy_path('/')", "/"),
    ("result = tidy_path('a//b/')", "a/b"),
    ("result = tidy_path('./')", "."),
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
