"""Unit tests for Stage 1 self-index fidelity fix.

Covers two measurement bugs fixed in self_index.py:
1. `_read_coverage()` was blind to the chain-test result schema (only read matrix_results),
   silently picking a stale/wrong file and reporting 0 verified.
2. `_run_validator_json()` mis-parsed validate_system.py's multi-line --json output and treated
   any nonzero returncode (which validate_system.py returns whenever any check FAILs — expected,
   not a run failure) as an absent signal, hiding real validator_fail weaknesses.
"""

from __future__ import annotations

import json
import subprocess

from tests.benchmarks.bench_security.scoring import classify_effort_tier
from tests.benchmarks.bench_security.self_index import (
    _SELF_DIR,
    _coverage_from_chain,
    _coverage_from_matrix,
    _read_coverage,
    _read_validator_health,
    _run_validator_json,
    build_self_index,
)


def _chain_entry(*, lab_success=False, refused=False, unique_coverage=0.0, scenario="s") -> dict:
    return {
        "scenario": scenario,
        "lab_success": lab_success,
        "refused": refused,
        "unique_coverage": unique_coverage,
    }


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


class TestCoverageFromChain:
    def test_counts_resolved_and_verified_strictly_from_lab_success(self):
        entries = [_chain_entry(lab_success=True) for _ in range(20)] + [
            _chain_entry(lab_success=False, refused=True),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.7),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.1),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.0),
        ]
        cov = _coverage_from_chain({"chain_tests": entries})

        assert cov["resolved"] == 24
        assert cov["verified"] == 20

        # Tier tally must match classify_effort_tier's own branching (not reimplemented here).
        expected_tally = {
            "verified_success": 0,
            "refused": 0,
            "honest_partial": 0,
            "minimal_attempt": 0,
        }
        for e in entries:
            expected_tally[classify_effort_tier(e)] += 1
        assert cov["tier_tally"] == expected_tally
        assert cov["tier_tally"]["verified_success"] == 20

    def test_none_when_no_chain_tests(self):
        assert _coverage_from_chain({"chain_tests": []}) is None
        assert _coverage_from_chain({}) is None

    def test_never_fabricates_verified_from_partial_success(self):
        """unique_coverage alone (honest_partial) must never count toward verified."""
        entries = [_chain_entry(lab_success=False, unique_coverage=0.9) for _ in range(5)]
        cov = _coverage_from_chain({"chain_tests": entries})
        assert cov["verified"] == 0
        assert cov["tier_tally"]["honest_partial"] == 5


class TestCoverageFromMatrix:
    def test_extracts_flat_matrix_fields(self):
        data = {
            "matrix_results": {
                "total_units": 10,
                "verified": 3,
                "rejected": 2,
                "indeterminate": 5,
                "pass_rate": 0.3,
            }
        }
        cov = _coverage_from_matrix(data)
        assert cov["resolved"] == 10
        assert cov["verified"] == 3

    def test_none_when_matrix_empty_or_zero(self):
        assert _coverage_from_matrix({"matrix_results": {}}) is None
        assert _coverage_from_matrix({"matrix_results": {"total_units": 0}}) is None
        assert _coverage_from_matrix({}) is None


class TestReadCoverageSelection:
    def test_picks_newest_real_coverage_across_both_dirs_and_schemas(self, monkeypatch, tmp_path):
        results_dir = tmp_path / "results"
        extra_dir = tmp_path / "extra_results"
        results_dir.mkdir()
        extra_dir.mkdir()
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._RESULTS_DIR", results_dir)
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._EXTRA_RESULTS_DIR", extra_dir
        )

        # Older matrix file with zero coverage in results_dir.
        old = results_dir / "sec_bench_20260101T000000Z.json"
        old.write_text(json.dumps({"matrix_results": {"total_units": 0}}))

        # A .partial.json checkpoint (bare list) sitting right next to it — must be skipped,
        # not raise, even though it has no dict structure at all.
        partial = results_dir / "sec_bench_20260101T000100Z.partial.json"
        partial.write_text(json.dumps([{"workspace": "auto-security", "status": "ok"}]))

        # Newer chain-test file in the *other* dir — must win regardless of which dir it's in.
        entries = [_chain_entry(lab_success=True) for _ in range(20)] + [
            _chain_entry(lab_success=False) for _ in range(4)
        ]
        newest = extra_dir / "sec_bench_20260102T000000Z.json"
        newest.write_text(json.dumps({"chain_tests": entries, "matrix_results": {}}))

        cov = _read_coverage()
        assert cov["status"] == "present"
        assert cov["source"] == newest.name
        assert cov["total_units"] == 24
        assert cov["verified"] == 20

    def test_stale_when_only_empty_files_present(self, monkeypatch, tmp_path):
        results_dir = tmp_path / "results"
        extra_dir = tmp_path / "extra_results"
        results_dir.mkdir()
        extra_dir.mkdir()
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._RESULTS_DIR", results_dir)
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._EXTRA_RESULTS_DIR", extra_dir
        )
        empty = results_dir / "sec_bench_20260101T000000Z.json"
        empty.write_text(json.dumps({"matrix_results": {}, "chain_tests": []}))

        cov = _read_coverage()
        assert cov["status"] in ("stale", "absent")


class TestValidatorJsonParsing:
    def test_parses_multiline_pretty_printed_json_with_preamble(self, monkeypatch):
        """Reproduces the real bug shape: non-JSON preamble text + indent=2 JSON block."""
        payload = {
            "elapsed_ms": 100,
            "passes": 20,
            "fails": 4,
            "warns": 0,
            "skips": 2,
            "results": [{"name": "A. python imports", "status": "FAIL", "detail": "boom"}],
        }
        stdout = "some preamble line\nanother non-json line\n" + json.dumps(payload, indent=2)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeCompletedProcess(1, stdout))

        data = _run_validator_json()
        assert data is not None
        assert data["passes"] == 20
        assert data["fails"] == 4

    def test_nonzero_returncode_is_not_treated_as_absent(self, monkeypatch):
        """validate_system.py exits 1 whenever fails > 0 — that's real signal, not a crash."""
        payload = {"elapsed_ms": 1, "passes": 1, "fails": 1, "warns": 0, "skips": 0, "results": []}
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(1, json.dumps(payload, indent=2)),
        )
        health = _read_validator_health()
        assert health["status"] == "present"
        assert health["fails"] == 1

    def test_empty_stdout_is_honestly_absent(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeCompletedProcess(1, ""))
        assert _run_validator_json() is None
        health = _read_validator_health()
        assert health["status"] == "absent"
        assert health["passes"] == 0

    def test_unparseable_stdout_is_honestly_absent(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _FakeCompletedProcess(1, "not json at all")
        )
        assert _run_validator_json() is None


class TestAntiRecursionGuard:
    def test_nested_env_var_still_passed(self, monkeypatch):
        """Guards commit 605845d's fork bug: the nested-run env var must still be set."""
        captured = {}

        def _fake_run(*args, **kwargs):
            captured.update(kwargs)
            return _FakeCompletedProcess(0, json.dumps({"passes": 1, "fails": 0, "results": []}))

        monkeypatch.setattr(subprocess, "run", _fake_run)
        _run_validator_json()
        assert captured["env"].get("PORTAL5_SELF_INDEX_NESTED") == "1"


class TestReadOnlyGuarantee:
    def test_no_writes_outside_report(self, monkeypatch, tmp_path):
        empty = tmp_path / "empty_no_writes"
        empty.mkdir()
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._RESULTS_DIR", empty)
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._EXTRA_RESULTS_DIR", empty)
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._JOURNAL_DIR", empty)
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                0, json.dumps({"passes": 1, "fails": 0, "warns": 0, "skips": 0, "results": []})
            ),
        )

        files_before = {p.name for p in _SELF_DIR.glob("*") if p.is_file()}
        dirs_before = {p.name for p in _SELF_DIR.glob("*") if p.is_dir()}

        build_self_index()

        files_after = {p.name for p in _SELF_DIR.glob("*") if p.is_file()}
        dirs_after = {p.name for p in _SELF_DIR.glob("*") if p.is_dir()}
        assert not (files_after - files_before)
        assert not (dirs_after - dirs_before)
