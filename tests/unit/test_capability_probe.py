"""Unit coverage for capability_probe scoring + code extraction (no live calls)."""

import importlib.util

spec = importlib.util.spec_from_file_location(
    "capability_probe", "tests/scripts/capability_probe.py"
)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def test_extract_longest_code_block():
    resp = "intro\n```python\nx=1\n```\nmid\n```python\ndef f():\n    return 42\n```\n"
    code = cp.extract_code(resp)
    assert "def f()" in code


def test_extract_none_when_no_block():
    assert cp.extract_code("just prose, no code") is None


def test_score_execution_pass():
    ok, _ = cp.score_execution({"stdout": "D1_OK\n", "exit_code": 0, "timed_out": False}, "D1_OK")
    assert ok


def test_score_execution_fail_on_missing_stdout():
    ok, detail = cp.score_execution({"stdout": "", "exit_code": 0, "timed_out": False}, "D1_OK")
    assert not ok and "not in stdout" in detail


def test_score_execution_fail_on_timeout():
    ok, detail = cp.score_execution({"stdout": "", "timed_out": True}, "X")
    assert not ok and "timed out" in detail
