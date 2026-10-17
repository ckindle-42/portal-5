"""Hidden graded suite for code-fix-06. The model never sees this file and cannot write to the
directory it runs in. Expected values are computed from the reference solution."""

import builtins

import pytest
import slugs as mod

CASES = [
    ("result = slugify('Hello,  World!')", "hello-world"),
    ("result = slugify('Plain')", "plain"),
    ("result = slugify('  lead and trail  ')", "lead-and-trail"),
    ("result = slugify('a--b')", "a-b"),
    ("result = slugify('!!!')", ""),
    ("result = slugify('Rust 2021 Edition')", "rust-2021-edition"),
    ("result = slugify('')", ""),
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
