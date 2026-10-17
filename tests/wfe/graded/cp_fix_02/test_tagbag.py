"""Hidden graded suite for code-fix-02. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import tagbag as mod

CASES = [
    ("result = add_tag('a')", ["a"]),
    ("result = add_tag('b')", ["b"]),
    ("result = add_tag('c', ['x'])", ["x", "c"]),
    ("result = add_tag('d')", ["d"]),
    ("result = add_tag('e', [])", ["e"]),
    ("result = add_tag('f')", ["f"]),
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
