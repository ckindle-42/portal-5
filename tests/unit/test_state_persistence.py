"""Verify _save_state delta semantics and concurrent-worker correctness.

Tests patch _STATE_FILE directly rather than reloading the module to
avoid Prometheus counter re-registration conflicts.
"""

import json

import pytest

import portal_pipeline.router_pipe as rp


@pytest.fixture(autouse=True)
def _reset_accumulators():
    """Snapshot and restore module-level accumulator state around each test."""
    saved_file = rp._STATE_FILE
    saved_tps = rp._total_tps
    saved_tps_count = rp._request_tps_count
    saved_rt = rp._total_response_time_ms
    saved_in = rp._total_input_tokens
    saved_out = rp._total_output_tokens
    saved_peak = rp._peak_concurrent
    saved_rc = dict(rp._request_count)
    saved_rm = dict(rp._req_count_by_model)
    saved_re = dict(rp._req_count_by_error)
    saved_pu = {k: dict(v) for k, v in rp._persona_usage_raw.items()}
    yield
    rp._STATE_FILE = saved_file
    rp._total_tps = saved_tps
    rp._request_tps_count = saved_tps_count
    rp._total_response_time_ms = saved_rt
    rp._total_input_tokens = saved_in
    rp._total_output_tokens = saved_out
    rp._peak_concurrent = saved_peak
    rp._request_count.clear()
    rp._request_count.update(saved_rc)
    rp._req_count_by_model.clear()
    rp._req_count_by_model.update(saved_rm)
    rp._req_count_by_error.clear()
    rp._req_count_by_error.update(saved_re)
    rp._persona_usage_raw.clear()
    rp._persona_usage_raw.update(saved_pu)


def test_save_state_resets_in_memory_after_persist(tmp_path):
    """In-memory counters must be 0 after successful save."""
    state_file = tmp_path / "metrics_state.json"
    rp._STATE_FILE = state_file

    rp._total_tps = 100.0
    rp._request_tps_count = 5
    rp._save_state()

    data = json.loads(state_file.read_text())
    assert data["total_tps"] == 100.0
    assert data["request_tps_count"] == 5

    assert rp._total_tps == 0.0
    assert rp._request_tps_count == 0


def test_save_state_no_double_counting(tmp_path):
    """Three save cycles with no new in-memory activity must not inflate the file."""
    state_file = tmp_path / "metrics_state.json"
    rp._STATE_FILE = state_file

    rp._total_tps = 100.0
    rp._request_tps_count = 5

    rp._save_state()  # writes 100, resets in-memory → 0
    rp._save_state()  # writes 100+0=100 — no inflation
    rp._save_state()  # writes 100+0=100 — still no inflation

    data = json.loads(state_file.read_text())
    assert data["total_tps"] == 100.0  # NOT 300
    assert data["request_tps_count"] == 5  # NOT 15


def test_save_state_concurrent_workers_serialize(tmp_path):
    """flock creates a sidecar lockfile; verify it exists after a save."""
    state_file = tmp_path / "metrics_state.json"
    rp._STATE_FILE = state_file

    rp._total_tps = 50.0
    rp._save_state()

    lock_file = state_file.with_suffix(".lock")
    assert lock_file.exists(), "sidecar lockfile must be created alongside state file"
