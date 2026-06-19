"""Empty-response retry guard for the TPS bench harness.

Verifies that a single 'empty response (0 tokens)' transient is retried once,
and that a successful retry promotes the cell to runs_success. Timeouts and
HTTP errors must NOT be retried.

NOTE: _stream_one_run is a closure inside bench_tps(), not a module-level
attribute, so these tests replicate the _run_with_empty_retry logic inline
rather than monkeypatching. They exercise the exact guard expression from
measure.py so the branch conditions stay consistent.
"""


def _make_stub(sequence):
    """Return a _stream_one_run stub that yields queued results in order."""
    calls = {"n": 0}

    def _stub(run_num):
        i = calls["n"]
        calls["n"] += 1
        return dict(sequence[i], run=run_num)

    return _stub, calls


def _run_with_empty_retry(stub, run_num):
    """Replicate the guard logic from measure.py _run_with_empty_retry."""
    result = stub(run_num)
    if result.get("error") == "empty response (0 tokens)":
        result = stub(run_num)
    return result


def test_empty_then_success_is_retried():
    stub, calls = _make_stub([
        {"error": "empty response (0 tokens)", "elapsed_s": 1.0},
        {"tps": 30.0, "completion_tokens": 100, "elapsed_s": 3.3},
    ])
    result = _run_with_empty_retry(stub, 1)
    assert "tps" in result, "successful retry should promote to success"
    assert calls["n"] == 2, "should have retried exactly once"


def test_timeout_is_not_retried():
    stub, calls = _make_stub([
        {"error": "timeout", "elapsed_s": 600.0},
        {"tps": 30.0, "completion_tokens": 100, "elapsed_s": 3.3},
    ])
    result = _run_with_empty_retry(stub, 1)
    assert result["error"] == "timeout"
    assert calls["n"] == 1, "timeout must not be retried"


def test_double_empty_records_failure():
    stub, calls = _make_stub([
        {"error": "empty response (0 tokens)", "elapsed_s": 1.0},
        {"error": "empty response (0 tokens)", "elapsed_s": 1.0},
    ])
    result = _run_with_empty_retry(stub, 1)
    assert result["error"] == "empty response (0 tokens)"
    assert calls["n"] == 2, "retry once, then accept failure"
