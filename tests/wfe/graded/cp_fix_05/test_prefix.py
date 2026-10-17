"""Hidden graded suite for code-fix-05. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import prefix as mod
import pytest

CASES = [
    ("result = common_prefix(['flower', 'flow', 'flight'])", "fl"),
    ("result = common_prefix(['same', 'same'])", "same"),
    ("result = common_prefix([])", ""),
    ("result = common_prefix(['solo'])", "solo"),
    ("result = common_prefix(['abc', 'abd', 'xyz'])", ""),
    ("result = common_prefix(['', 'a'])", ""),
    ("result = common_prefix(['interview', 'internet', 'internal'])", "inter"),
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
