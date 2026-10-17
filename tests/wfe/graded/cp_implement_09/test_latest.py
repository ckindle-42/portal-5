"""Hidden graded suite for code-implement-09. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import latest as mod
import pytest

CASES = [
    ("result = keep_latest([], 'id')", []),
    (
        "result = keep_latest([{'id': 1, 'v': 'a'}, {'id': 2, 'v': 'b'}, {'id': 1, 'v': 'c'}], 'id')",
        [{"id": 2, "v": "b"}, {"id": 1, "v": "c"}],
    ),
    ("result = keep_latest([{'v': 1}, {'v': 2}], 'id')", [{"v": 1}, {"v": 2}]),
    ("result = keep_latest([{'id': 1}, {'x': 1}, {'id': 1}], 'id')", [{"x": 1}, {"id": 1}]),
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
