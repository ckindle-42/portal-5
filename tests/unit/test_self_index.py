"""Unit tests for Stage 1 self-legibility index — read-only enforcement, deterministic ranking."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# ── Fixture: minimal index data ──────────────────────────────────────────────


@pytest.fixture
def sample_validator_json() -> dict:
    return {
        "passes": 23,
        "fails": 1,
        "warns": 1,
        "skips": 1,
        "elapsed_ms": 5200,
        "results": [
            {
                "name": "A. python imports",
                "status": "PASS",
                "detail": "all 12 imports ok",
                "elapsed_ms": 234,
            },
            {
                "name": "B. pipeline assembles",
                "status": "FAIL",
                "detail": "missing routes",
                "elapsed_ms": 12,
            },
            {"name": "C. config round-trip", "status": "PASS", "detail": "ok", "elapsed_ms": 45},
        ],
    }


@pytest.fixture
def sample_journal_entries(tmp_path) -> Path:
    """Create sample journal entries in a tmp_path."""
    journal_dir = tmp_path / "field_journal"
    journal_dir.mkdir()
    entries = [
        {
            "engagement_id": "test-001",
            "ts": "2026-07-01T00:00:00Z",
            "scenario_category": "ad",
            "goal": "kerberoast",
            "execution_chain": [{"step": "nmap", "tool": "run_nmap_scan"}],
            "pitfalls": [
                {"problem": "network timeout", "cause": "lab", "resolution": "retry"},
                {"problem": "network timeout", "cause": "lab", "resolution": "retry"},
                {"problem": "auth failure", "cause": "creds", "resolution": "reset"},
            ],
            "reusable": [],
            "outcome": "goal_met",
            "proven_coverage": {},
            "verified_findings": [],
        },
        {
            "engagement_id": "test-002",
            "ts": "2026-07-01T01:00:00Z",
            "scenario_category": "ad",
            "goal": "asrep",
            "execution_chain": [{"step": "asrep", "tool": "GetNPUsers"}],
            "pitfalls": [
                {"problem": "network timeout", "cause": "lab", "resolution": "retry"},
            ],
            "reusable": [],
            "outcome": "partial",
            "proven_coverage": {},
            "verified_findings": [],
        },
    ]
    for e in entries:
        p = journal_dir / f"{e['ts'][:10]}_{e['scenario_category']}_{e['engagement_id']}.json"
        p.write_text(json.dumps(e))
    # Also create index
    index = {
        "generated_at": "2026-07-01T01:00:00Z",
        "total_entries": 2,
        "by_category": {"ad": 2},
        "outcomes": {"goal_met": 1, "partial": 1},
        "top_pitfalls": [{"problem": "network timeout", "file": "test-001.json"}],
    }
    (journal_dir / "_index.json").write_text(json.dumps(index))
    return journal_dir


# ── Test: build_self_index reads fixtures, never writes ───────────────────────


class TestBuildSelfIndex:
    def test_reads_validator_health(self, sample_validator_json, monkeypatch, tmp_path):
        """Validator health returns structured view with checks."""
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_run(sample_validator_json))
        from tests.benchmarks.bench_security.self_index import _read_validator_health

        health = _read_validator_health()
        assert health["status"] == "present"
        assert health["passes"] == 23
        assert health["fails"] == 1
        assert "A. python imports" in health["checks"]
        assert health["checks"]["B. pipeline assembles"]["status"] == "FAIL"

    def test_reads_oracle_fidelity_registry(self, monkeypatch):
        """Oracle fidelity reads the ORACLES registry directly — always present."""
        from tests.benchmarks.bench_security.self_index import _read_oracle_fidelity

        fidelity = _read_oracle_fidelity()
        assert fidelity["status"] == "present"
        assert fidelity["total_oracles"] > 0
        assert "stable" in fidelity["tiers"]
        assert fidelity["stable_count"] > 0
        for _oid, odata in fidelity["oracles"].items():
            assert "tier" in odata
            assert "kind" in odata

    def test_coverage_stale_when_no_results(self, monkeypatch, tmp_path):
        """Coverage reports stale when no recent bench results exist."""
        from tests.benchmarks.bench_security.self_index import _read_coverage

        empty_results_dir = tmp_path / "empty_results"
        empty_results_dir.mkdir()
        empty_extra_dir = tmp_path / "empty_extra_results"
        empty_extra_dir.mkdir()
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._RESULTS_DIR", empty_results_dir
        )
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._EXTRA_RESULTS_DIR", empty_extra_dir
        )
        coverage = _read_coverage()
        assert coverage["status"] in ("stale", "absent")

    def test_discipline_breadth_present(self):
        """Discipline breadth reads from PROMPTS — always present."""
        from tests.benchmarks.bench_security.self_index import _read_discipline_breadth

        disc = _read_discipline_breadth()
        assert disc["status"] == "present"
        assert len(disc["disciplines"]) > 0
        for _domain, ddata in disc["disciplines"].items():
            assert "red" in ddata
            assert "blue" in ddata

    def test_journal_absent_when_no_entries(self, monkeypatch, tmp_path):
        """Journal returns absent when no entries exist."""
        from tests.benchmarks.bench_security.self_index import _read_journal_summary

        empty_journal = tmp_path / "empty_journal"
        empty_journal.mkdir()
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._JOURNAL_DIR", empty_journal
        )
        journal = _read_journal_summary()
        assert journal["status"] == "absent"
        assert journal["total_entries"] == 0

    def test_journal_reads_index(self, sample_journal_entries, monkeypatch):
        """Journal summary reads from _index.json when present."""
        from tests.benchmarks.bench_security.self_index import _read_journal_summary

        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._JOURNAL_DIR", sample_journal_entries
        )
        journal = _read_journal_summary()
        assert journal["status"] == "present"
        assert journal["total_entries"] == 2
        assert journal["by_category"]["ad"] == 2

    def test_journal_reads_entries_without_index(self, sample_journal_entries, monkeypatch):
        """Journal summary reads raw entries when _index.json is missing."""
        from tests.benchmarks.bench_security.self_index import _read_journal_summary

        # Remove the index file
        (sample_journal_entries / "_index.json").unlink()
        monkeypatch.setattr(
            "tests.benchmarks.bench_security.self_index._JOURNAL_DIR", sample_journal_entries
        )
        journal = _read_journal_summary()
        assert journal["status"] == "stale"
        assert journal["total_entries"] == 2

    def test_build_self_index_structure(self):
        """Full build_self_index returns all five top-level keys."""
        from tests.benchmarks.bench_security.self_index import build_self_index

        index = build_self_index()
        assert set(index.keys()) == {
            "validator",
            "oracles",
            "coverage",
            "disciplines",
            "journal",
            "generated_at",
        }
        assert "generated_at" in index
        assert isinstance(index["generated_at"], str)

    def test_read_only_no_writes_outside_report(self, monkeypatch, tmp_path):
        """build_self_index performs no filesystem writes (read-only guarantee)."""
        from tests.benchmarks.bench_security.self_index import (
            _SELF_DIR,
            build_self_index,
        )

        # Point all directories to empty tmp_paths
        empty = tmp_path / "empty_no_writes"
        empty.mkdir()
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._RESULTS_DIR", empty)
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._JOURNAL_DIR", empty)
        # Also patch the validator subprocess to avoid real execution
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _fake_run_validator())

        # Record state of SELF_DIR before
        files_before = {p.name for p in _SELF_DIR.glob("*") if p.is_file()}
        dirs_before = {p.name for p in _SELF_DIR.glob("*") if p.is_dir()}

        index = build_self_index()

        # After: no new files/dirs created in bench_security directory
        files_after = {p.name for p in _SELF_DIR.glob("*") if p.is_file()}
        dirs_after = {p.name for p in _SELF_DIR.glob("*") if p.is_dir()}

        new_files = files_after - files_before
        new_dirs = dirs_after - dirs_before
        assert not new_files, f"build_self_index wrote unexpected files: {new_files}"
        assert not new_dirs, f"build_self_index created unexpected dirs: {new_dirs}"

        # Index structure is still valid
        assert "validator" in index
        assert "oracles" in index


# ── Test: rank_weaknesses — deterministic, transparent score ──────────────────


class TestRankWeaknesses:
    @pytest.fixture
    def sample_index(self) -> dict:
        return {
            "validator": {
                "status": "present",
                "passes": 24,
                "fails": 2,
                "checks": {
                    "A. python imports": {"status": "PASS", "detail": "ok"},
                    "B. pipeline assembles": {"status": "FAIL", "detail": "missing /v1/foo"},
                    "X. scenario-oracle": {"status": "FAIL", "detail": "3 issues"},
                    "Z. new check": {"status": "PASS", "detail": "ok"},
                },
            },
            "oracles": {
                "status": "present",
                "total_oracles": 5,
                "stable_count": 3,
                "heuristic_count": 2,
                "tiers": {"stable": 3, "experimental": 1, "oob": 1},
                "oracles": {
                    "reflection": {"kind": "unescaped_reflection", "tier": "stable"},
                    "sqli_boolean": {"kind": "boolean_differential", "tier": "stable"},
                    "oast_callback": {"kind": "out_of_band", "tier": "experimental"},
                    "ptai_ssrf_metadata": {"kind": "ssrf_oob", "tier": "oob"},
                    "cve_confirmed": {"kind": "cve_signature", "tier": "stable"},
                },
            },
            "coverage": {
                "status": "stale",
                "by_class": {
                    "sqli": {
                        "resolved": 5,
                        "ran": 5,
                        "verified": 0,
                        "rejected": 5,
                        "domain": "web",
                    },
                    "xss": {"resolved": 4, "ran": 0, "verified": 0, "rejected": 0, "domain": "web"},
                    "deserial": {
                        "resolved": 3,
                        "ran": 3,
                        "verified": 2,
                        "rejected": 1,
                        "domain": "web",
                    },
                },
                "by_scenario": {
                    "web_test": {
                        "resolved": 1,
                        "ran": 1,
                        "verified": 0,
                        "rejected": 0,
                        "oracle": None,
                    },
                    "ad_test": {
                        "resolved": 1,
                        "ran": 1,
                        "verified": 1,
                        "rejected": 0,
                        "oracle": "reflection",
                    },
                },
            },
            "disciplines": {
                "status": "present",
                "disciplines": {
                    "web": {
                        "scenario_count": 10,
                        "red": True,
                        "blue": True,
                        "purple": True,
                        "status": "full_spectrum",
                    },
                    "ad": {
                        "scenario_count": 5,
                        "red": True,
                        "blue": False,
                        "purple": False,
                        "status": "red_only",
                    },
                    "cloud": {
                        "scenario_count": 0,
                        "red": False,
                        "blue": False,
                        "purple": False,
                        "status": "absent",
                    },
                },
            },
            "journal": {
                "status": "present",
                "total_entries": 5,
                "top_pitfalls": [
                    {"problem": "network timeout", "file": "a.json"},
                    {"problem": "network timeout", "file": "b.json"},
                    {"problem": "auth failure", "file": "c.json"},
                ],
            },
        }

    def test_ranking_includes_failing_checks(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        failing = [w for w in weaknesses if w["kind"] == "failing_check"]
        assert len(failing) == 2
        assert failing[0]["score"] == 30

    def test_ranking_includes_heuristic_oracles(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        heuristic_oracles = [w for w in weaknesses if w["kind"].startswith("oracle_tier_")]
        assert len(heuristic_oracles) == 2
        # oob tier scores higher than experimental
        oob = [w for w in heuristic_oracles if "oob" in w["kind"]]
        exp = [w for w in heuristic_oracles if "experimental" in w["kind"]]
        assert len(oob) == 1
        assert len(exp) == 1
        assert oob[0]["score"] == 20  # oracle_oob
        assert exp[0]["score"] == 10  # oracle_experimental

    def test_ranking_includes_zero_verified_classes(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        zero_verified = [w for w in weaknesses if w["kind"] == "class_zero_verified"]
        assert len(zero_verified) == 1
        assert zero_verified[0]["area"] == "class:sqli"
        assert zero_verified[0]["score"] == 25

    def test_ranking_includes_red_machines(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        red_machines = [w for w in weaknesses if w["kind"] == "machine_red_coverage"]
        assert len(red_machines) == 1
        assert red_machines[0]["area"] == "class:xss"
        assert red_machines[0]["score"] == 25

    def test_ranking_includes_discipline_gaps(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        red_only = [w for w in weaknesses if w["kind"] == "discipline_red_only"]
        absent = [w for w in weaknesses if w["kind"] == "discipline_absent"]
        assert len(red_only) == 1
        assert red_only[0]["area"] == "discipline:ad"
        assert len(absent) == 1
        assert absent[0]["area"] == "discipline:cloud"

    def test_ranking_includes_recurring_journal_failures(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        journal_weak = [w for w in weaknesses if w["kind"] == "journal_recurring_failure"]
        assert len(journal_weak) == 1
        assert journal_weak[0]["score"] == 10
        assert "network timeout" in journal_weak[0]["evidence"]

    def test_ranking_includes_heuristic_only_scenarios(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        heuristic_scenarios = [w for w in weaknesses if w["kind"] == "scenario_heuristic_only"]
        assert len(heuristic_scenarios) == 1
        assert heuristic_scenarios[0]["area"] == "scenario:web_test"
        assert heuristic_scenarios[0]["score"] == 15

    def test_ranking_deterministic_ordering(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        w1 = rank_weaknesses(sample_index)
        w2 = rank_weaknesses(sample_index)
        assert w1 == w2

    def test_ranking_score_formula_inspectable(self, sample_index):
        from tests.benchmarks.bench_security.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        for w in weaknesses:
            assert "score" in w
            assert "why" in w
            assert "area" in w
            assert "kind" in w
            assert "evidence" in w
            # Score must come from the documented _SCORE_RULES
            assert isinstance(w["score"], int)

    def test_absent_signals_marked_not_fabricated(self, monkeypatch, tmp_path):
        """When signals are absent, they are marked as such — no invented counts."""
        from tests.benchmarks.bench_security.self_index import build_self_index, rank_weaknesses

        # Mock subprocess to avoid running real validator
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _FakeCompletedProcess(
                0,
                json.dumps(
                    {
                        "passes": 26,
                        "fails": 0,
                        "warns": 0,
                        "skips": 0,
                        "elapsed_ms": 1,
                        "results": [],
                    }
                ),
            ),
        )
        # Point results/journal dirs to empty tmp dirs
        empty = tmp_path / "empty_no_data"
        empty.mkdir()
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._RESULTS_DIR", empty)
        monkeypatch.setattr("tests.benchmarks.bench_security.self_index._JOURNAL_DIR", empty)

        index = build_self_index()
        # coverage may be stale/absent if no recent results — no fabricated VERIFIED counts
        coverage = index["coverage"]
        assert coverage["status"] in ("present", "stale", "absent")
        if coverage["status"] == "absent":
            assert coverage["total_units"] == 0
            assert coverage["verified"] == 0

        # Weakness ranking still works with absent signals
        weaknesses = rank_weaknesses(index)
        assert isinstance(weaknesses, list)


# ── Helpers ───────────────────────────────────────────────────────────────────


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout):
        self.returncode = returncode
        self.stdout = stdout


def _fake_run(data: dict):
    return _FakeCompletedProcess(0, json.dumps(data))


def _fake_run_validator():
    return _FakeCompletedProcess(
        0,
        json.dumps(
            {
                "passes": 26,
                "fails": 0,
                "warns": 0,
                "skips": 0,
                "elapsed_ms": 5000,
                "results": [
                    {"name": f"check_{i}", "status": "PASS", "detail": "ok"} for i in range(26)
                ],
            }
        ),
    )
