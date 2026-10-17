"""Hidden graded suite for code-refactor-02. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import orders as mod
import pytest

CASES = [
    ('result = process({"id": 1, "items": [(5, 2)]})', {"ok": True, "total": 10}),
    ("result = process({})", {"ok": False, "errors": ["missing id", "no items"]}),
    ('result = process({"id": 2, "items": [(5, 0)]})', {"ok": False, "errors": ["bad quantity"]}),
    ('result = validate_order({"id": 1, "items": [(5, 2)]})', []),
    ("result = validate_order({})", ["missing id", "no items"]),
    ('result = validate_order({"items": [(5, -1)]})', ["missing id", "bad quantity"]),
    ('result = process({"id": 3, "items": []})', {"ok": False, "errors": ["no items"]}),
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
