"""Tests for OS-aware SPL variants — Phase A.

Validates:
- spl_variants field works in YAML
- spl_for() selects correct variant by source
- Backward compatibility (single spl still works)
- Affected techniques have Windows 4688 variants
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "benchmarks"))

from portal.modules.security.core.siem.spl_detections import (
    _invalidate_cache,
    spl_for,
    spl_variants_for,
    techniques_covered,
)


class TestSPLVariants:
    """OS-aware SPL variants for cross-platform detection."""

    def test_spl_for_with_source_selects_variant(self):
        _invalidate_cache()
        # T1059 should have a windows:security variant
        spl_linux = spl_for("T1059", source="linux:auditd")
        spl_win = spl_for("T1059", source="windows:security")
        assert spl_linux is not None
        assert spl_win is not None
        assert "linux:auditd" in spl_linux
        assert "windows:security" in spl_win
        assert spl_linux != spl_win  # different variants

    def test_spl_for_without_source_returns_default(self):
        _invalidate_cache()
        spl = spl_for("T1059")
        assert spl is not None
        assert "linux:auditd" in spl  # default is Linux

    def test_spl_for_backward_compat(self):
        _invalidate_cache()
        # T1558.003 has no variants — should still work
        spl = spl_for("T1558.003")
        assert spl is not None
        assert "4769" in spl

    def test_spl_variants_for(self):
        _invalidate_cache()
        variants = spl_variants_for("T1059")
        assert len(variants) == 2
        sources = [v["source"] for v in variants]
        assert "linux:auditd" in sources
        assert "windows:security" in sources

    def test_spl_variants_for_no_variants(self):
        _invalidate_cache()
        variants = spl_variants_for("T1558.003")
        assert variants == []

    def test_affected_techniques_have_windows_variants(self):
        """T1059, T1548.001, T1068, T1210, T1021.002 should have Windows variants."""
        _invalidate_cache()
        affected = ["T1059", "T1548.001", "T1068", "T1210", "T1021.002"]
        for tid in affected:
            variants = spl_variants_for(tid)
            sources = [v["source"] for v in variants]
            assert "windows:security" in sources, f"{tid} missing windows:security variant"

    def test_t1190_has_iis_variant(self):
        """T1190 should have a web:access:iis variant for meta3."""
        _invalidate_cache()
        variants = spl_variants_for("T1190")
        sources = [v["source"] for v in variants]
        assert "web:access:iis" in sources, "T1190 missing IIS variant"

    def test_techniques_covered_unchanged(self):
        """Adding variants doesn't change the technique count."""
        _invalidate_cache()
        covered = techniques_covered()
        assert len(covered) >= 29

    def test_variant_spl_is_valid_string(self):
        """Every variant's SPL is a non-empty string."""
        _invalidate_cache()
        for tid in techniques_covered():
            variants = spl_variants_for(tid)
            for v in variants:
                assert isinstance(v["spl"], str) and v["spl"], f"{tid} variant has empty SPL"
                assert isinstance(v["source"], str) and v["source"], (
                    f"{tid} variant has empty source"
                )
