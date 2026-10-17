"""Hidden graded suite for code-fix-07. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import wc as mod

CASES = [
    ("result = count_words('Go go, GO!')", {"go": 3}),
    ("result = count_words('one two one')", {"one": 2, "two": 1}),
    ("result = count_words('')", {}),
    ("result = count_words(\"It's it's, IT'S.\")", {"it's": 3}),
    ("result = count_words('a b a. b? c')", {"a": 2, "b": 2, "c": 1}),
    ("result = count_words('42 forty-two 42')", {"42": 2, "forty": 1, "two": 1}),
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
