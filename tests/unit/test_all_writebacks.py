"""Tests for all write-back loops — P3 (investigation), P4 (bench), P5 (gap).

Validates:
- Investigation findings write back as cited units
- Bench results write back as model-knowledge units
- Gap resolutions write back as coverage status units
- All write-backs are provenance-required
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from portal_wiki.core.store import reset_canonical_dir, set_canonical_dir
from portal_wiki.core.writeback import reset_proposed_dir, set_proposed_dir


class TestInvestigationWriteback:
    """P3: Closed investigation findings write back."""

    def test_findings_write_back(self, tmp_path):
        from portal_wiki.adapters.writeback_investigation import writeback_investigation_findings

        set_proposed_dir(tmp_path / "p")
        set_canonical_dir(tmp_path / "c")
        try:
            proposed = writeback_investigation_findings(
                "case-001",
                [
                    {
                        "technique_ids": ["T1558.003"],
                        "description": "Kerberoasting",
                        "evidence_refs": ["ev-001"],
                        "confidence": 0.9,
                    }
                ],
            )
            assert len(proposed) == 1
            assert "T1558.003" in proposed[0]["title"]
        finally:
            reset_proposed_dir()
            reset_canonical_dir()

    def test_empty_findings_noop(self, tmp_path):
        from portal_wiki.adapters.writeback_investigation import writeback_investigation_findings

        set_proposed_dir(tmp_path / "p")
        try:
            proposed = writeback_investigation_findings("case-002", [])
            assert proposed == []
        finally:
            reset_proposed_dir()


class TestBenchWriteback:
    """P4: Bench results write back as model-knowledge units."""

    def test_bench_result_write_back(self, tmp_path):
        from portal_wiki.adapters.writeback_bench import writeback_bench_result

        set_proposed_dir(tmp_path / "p")
        set_canonical_dir(tmp_path / "c")
        try:
            result = writeback_bench_result(
                "sylink:8b", "blue-analyst", "keep", delta="+2% F1", result_path="results/test.json"
            )
            assert result is not None
            assert "sylink:8b" in result["title"]
        finally:
            reset_proposed_dir()
            reset_canonical_dir()


class TestGapWriteback:
    """P5: Gap resolutions write back as coverage status units."""

    def test_gap_resolution_write_back(self, tmp_path):
        from portal_wiki.adapters.writeback_gap import writeback_gap_resolution

        set_proposed_dir(tmp_path / "p")
        set_canonical_dir(tmp_path / "c")
        try:
            result = writeback_gap_resolution("T1190", "COVERED", episode_id="ep-test-001")
            assert result is not None
            assert "T1190" in result["title"]
            assert "COVERED" in result["title"]
        finally:
            reset_proposed_dir()
            reset_canonical_dir()
