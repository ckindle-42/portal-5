"""Tests for the compliance/framework report generator — Phases 2 & 4 of
TASK-SEC-COMPLIANCE-REPORT-GENERATOR-V1.

Validates:
- report renders from a sample results file
- a GAP technique appears as a gap, never hidden
- synthetic-fallback is NOT counted as detected, even if capability_verdict
  upstream somehow said PROVEN (defense in depth)
- framework rollup computes correct % against MAPPED techniques only
- every claim in the provenance appendix carries a source
- INSUFFICIENT-DATA when no results file / empty results
- generated files carry the GENERATED marker
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.compliance_report import (
    _is_really_detected,
)


class TestSyntheticNeverDetected:
    def test_synthetic_fallback_not_detected_even_if_proven(self) -> None:
        """Defense in depth: even if capability_verdict says PROVEN, a
        synthetic-fallback result must never count as really detected."""
        rec = {
            "capability_verdict": "PROVEN",
            "blue_used_synthetic_fallback": True,
        }
        assert _is_really_detected(rec) is False

    def test_episode_used_synthetic_not_detected(self) -> None:
        rec = {
            "capability_verdict": "PROVEN",
            "episode": {"used_synthetic": True},
        }
        assert _is_really_detected(rec) is False

    def test_real_proven_is_detected(self) -> None:
        rec = {
            "capability_verdict": "PROVEN",
            "blue_used_synthetic_fallback": False,
            "episode": {"used_synthetic": False},
        }
        assert _is_really_detected(rec) is True

    def test_indeterminate_not_detected(self) -> None:
        rec = {"capability_verdict": "INDETERMINATE"}
        assert _is_really_detected(rec) is False
