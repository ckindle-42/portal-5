"""Hidden graded suite for code-implement-05. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import common as mod
import pytest

CASES = [
    ("result = most_common(['b', 'a', 'b', 'c', 'a', 'd'], 2)", ["b", "a"]),
    ("result = most_common([], 3)", []),
    ("result = most_common([1, 1, 2, 2, 3], 5)", [1, 2, 3]),
    ("result = most_common(['x'], 0)", []),
    (
        "result = most_common(['m', 'i', 's', 's', 'i', 's', 's', 'i', 'p', 'p', 'i'], 3)",
        ["i", "s", "p"],
    ),
    ("result = most_common(['q', 'r'], -1)", []),
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
