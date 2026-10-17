"""Hidden graded suite for code-implement-02. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import clock as mod
import pytest

CASES = [
    ("result = parse_span_text('1h30m15s')", 5415),
    ("result = parse_span_text('45m')", 2700),
    ("result = parse_span_text('90s')", 90),
    ("result = parse_span_text('2h')", 7200),
    ("result = parse_span_text('')", ("__raises__", "ValueError")),
    ("result = parse_span_text('5x')", ("__raises__", "ValueError")),
    ("result = parse_span_text('30m1h')", ("__raises__", "ValueError")),
    ("result = parse_span_text('1h1h')", ("__raises__", "ValueError")),
    ("result = parse_span_text('15')", ("__raises__", "ValueError")),
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
