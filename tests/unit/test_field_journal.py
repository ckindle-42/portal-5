"""Unit tests for security field-journal (Gap 2)."""

from __future__ import annotations

import json

from tests.benchmarks.bench_security.field_journal import (
    rebuild_index,
    recall,
    record_engagement,
    write_entry,
)


class TestWriteEntry:
    def test_write_and_rebuild(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tests.benchmarks.bench_security.field_journal.JOURNAL_DIR", tmp_path)
        entry = {
            "engagement_id": "test-001",
            "ts": "2026-07-01T00:00:00Z",
            "scenario_category": "ad",
            "goal": "kerberoast",
            "execution_chain": [{"step": "nmap", "tool": "run_nmap_scan"}],
            "pitfalls": [{"problem": "timeout", "cause": "network", "resolution": "retry"}],
            "reusable": [{"pattern": "kerberoast", "snippet": "impacket..."}],
            "outcome": "goal_met",
            "proven_coverage": {},
            "verified_findings": [],
        }
        write_entry(entry)
        rebuild_index()
        assert len(list(tmp_path.glob("*.json"))) >= 2
        index = json.loads((tmp_path / "_index.json").read_text())
        assert index["total_entries"] == 1
        assert index["outcomes"]["goal_met"] == 1

    def test_entries_stamped(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tests.benchmarks.bench_security.field_journal.JOURNAL_DIR", tmp_path)
        entry = {
            "engagement_id": "test-002",
            "ts": "2026-07-01T01:00:00Z",
            "scenario_category": "web",
            "goal": "sqli",
            "execution_chain": [],
            "pitfalls": [],
            "reusable": [],
            "outcome": "failed",
            "proven_coverage": {},
            "verified_findings": [],
        }
        p = write_entry(entry)
        data = json.loads(p.read_text())
        assert "methodology_version" in data
        assert data["methodology_version"] == "v2-capability"


class TestRecall:
    def test_recall_matches_category_and_keywords(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tests.benchmarks.bench_security.field_journal.JOURNAL_DIR", tmp_path)
        e1 = {
            "engagement_id": "r1",
            "ts": "2026-07-01T00:00:00Z",
            "scenario_category": "ad",
            "goal": "kerberoast",
            "execution_chain": [{"step": "kerberoast", "tool": "exploit_service"}],
            "pitfalls": [],
            "reusable": [{"pattern": "kerberoast", "snippet": "impacket GetUserSPNs"}],
            "outcome": "goal_met",
            "proven_coverage": {},
            "verified_findings": [],
        }
        e2 = {
            "engagement_id": "r2",
            "ts": "2026-07-01T01:00:00Z",
            "scenario_category": "web",
            "goal": "sqli",
            "execution_chain": [{"step": "sqli", "tool": "check_cve"}],
            "pitfalls": [],
            "reusable": [],
            "outcome": "partial",
            "proven_coverage": {},
            "verified_findings": [],
        }
        write_entry(e1)
        write_entry(e2)
        rebuild_index()

        results = recall("ad")
        assert len(results) == 1
        assert results[0]["engagement_id"] == "r1"

        results = recall("ad", keywords=["impacket"])
        assert len(results) == 1

        results = recall("nonexistent")
        assert len(results) == 0


class TestRecordEngagement:
    def test_malformed_chain_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tests.benchmarks.bench_security.field_journal.JOURNAL_DIR", tmp_path)
        # Should not raise — empty chain is handled gracefully
        record_engagement({})
        # May write a minimal entry or return None — both are acceptable
        assert True  # no exception
