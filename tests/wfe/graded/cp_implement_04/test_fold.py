"""Hidden graded suite for code-implement-04. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import fold as mod
import pytest

CASES = [
    (
        "result = fold_lines('the quick brown fox jumps over', 10)",
        ["the quick", "brown fox", "jumps over"],
    ),
    ("result = fold_lines('', 5)", []),
    ("result = fold_lines('extraordinarily long word', 8)", ["extraordinarily", "long", "word"]),
    ("result = fold_lines('a b c', 1)", ["a", "b", "c"]),
    ("result = fold_lines('aa bb cc dd', 5)", ["aa bb", "cc dd"]),
    ("result = fold_lines('  spaced   out  ', 20)", ["spaced out"]),
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
