"""Hidden graded suite for code-kv. The model never sees this file and cannot
write to the directory it runs in — the previous task scored the model against
tests the model itself authored."""

from parse_kv import parse_kv


def test_basic():
    assert parse_kv("a=1; b=2") == {"a": "1", "b": "2"}


def test_trims_whitespace():
    assert parse_kv("  a = 1 ;  b = 2  ") == {"a": "1", "b": "2"}


def test_empty_string():
    assert parse_kv("") == {}


def test_escaped_semicolon_is_literal():
    assert parse_kv(r"note=a\;b; k=v") == {"note": "a;b", "k": "v"}


def test_value_may_contain_equals():
    assert parse_kv("url=http://x/?a=1") == {"url": "http://x/?a=1"}


def test_pair_without_equals_is_skipped_or_empty():
    out = parse_kv("a=1; junk; b=2")
    assert out.get("a") == "1" and out.get("b") == "2"
    assert out.get("junk", "") == ""


def test_trailing_separator():
    assert parse_kv("a=1;") == {"a": "1"}
