"""Hidden graded suite for code-refactor-04. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import rows as mod

CASES = [
    ('result = parse_line("bolt, 4, 0.25")', {"name": "bolt", "qty": 4, "price": 0.25}),
    ('result = parse_line(" nut ,10,1.5 ")', {"name": "nut", "qty": 10, "price": 1.5}),
    ('result = split_fields(" a , b ,c")', ["a", "b", "c"]),
    ('result = convert(["x", "2", "3.5"])', {"name": "x", "qty": 2, "price": 3.5}),
    ('result = parse_line("p,1,2")', {"name": "p", "qty": 1, "price": 2.0}),
    ('result = split_fields("a,b")', ("__raises__", "ValueError")),
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
