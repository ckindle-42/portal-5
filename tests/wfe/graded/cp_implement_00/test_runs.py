"""Hidden graded suite for code-implement-00. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import runs as mod

CASES = [
    ("result = squeeze_runs('')", []),
    ("result = squeeze_runs('aaabcc')", [("a", 3), ("b", 1), ("c", 2)]),
    ("result = squeeze_runs('aAa')", [("a", 1), ("A", 1), ("a", 1)]),
    ("result = squeeze_runs('z')", [("z", 1)]),
    ("result = squeeze_runs('112211')", [("1", 2), ("2", 2), ("1", 2)]),
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
