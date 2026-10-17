"""Hidden graded suite for code-refactor-03. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import ids as mod
import pytest

CASES = [
    ("result = next_id()", "id-1"),
    ('result = next_id("job")', "job-2"),
    ("result = next_id()", "id-3"),
    ("s = IdSource()\nresult = [s.next(), s.next('x')]", ["id-1", "x-2"]),
    ("t = IdSource(10)\nresult = t.next('t')", "t-11"),
    ("result = next_id('z')", "z-4"),
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
