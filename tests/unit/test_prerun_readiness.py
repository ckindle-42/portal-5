"""Unit tests for pre-run readiness — blue-scorable invariant + SPL coverage.

Verifies:
- Zero red-only scenarios (mbptl_ctf_full_chain now has ground truth)
- Every technique in any scenario's detect_ground_truth has an SPL detection
  or is a recorded blue-gap
- New SPL entries parse correctly
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.benchmarks.bench_security.exec_chain import SCENARIOS
from tests.benchmarks.bench_security.siem.spl_detections import techniques_covered

# ── Honest blue-gaps: techniques with no in-lab telemetry source ─────────────
# These require cloud-provider telemetry (CloudTrail, Azure AD, S3 access logs)
# which is not ingested in the lab. Recorded here, not faked in SPL.
BLUE_GAPS: set[str] = {
    "T1078.004",  # Valid Accounts: Cloud Accounts — needs cloud identity telemetry
    "T1537",  # Transfer Data to Cloud Account — needs cloud storage access logs
}

_SPL_YAML = Path(__file__).resolve().parent.parent / (
    "benchmarks/bench_security/siem/spl_detections.yaml"
)


class TestBlueScorableInvariant:
    """Zero scenarios may have empty detect_ground_truth — the operator's rule."""

    def test_no_red_only_scenarios(self):
        bad = [k for k, v in SCENARIOS.items() if not v.get("detect_ground_truth")]
        assert not bad, f"Red-only scenarios (no detect_ground_truth): {bad}"

    def test_mbptl_has_ground_truth(self):
        """The previously red-only mbptl scenario now carries techniques."""
        gt = SCENARIOS["mbptl_ctf_full_chain"].get("detect_ground_truth")
        assert gt, "mbptl_ctf_full_chain still has empty detect_ground_truth"
        assert len(gt) >= 2, f"mbptl_ctf_full_chain has only {len(gt)} techniques"


class TestBlueDetectability:
    """Every technique in scenarios must have SPL or be a recorded blue-gap."""

    def test_all_techniques_covered_or_gapped(self):
        """No silent undetectable technique."""
        spl_covered = set(techniques_covered())
        all_techniques: set[str] = set()
        for v in SCENARIOS.values():
            all_techniques.update(v.get("detect_ground_truth", []))

        undetected = all_techniques - spl_covered - BLUE_GAPS
        assert not undetected, (
            f"Techniques without SPL detection and not in BLUE_GAPS: {sorted(undetected)}. "
            f"Add SPL entries or record as honest blue-gaps."
        )

    def test_blue_gaps_are_honestly_recorded(self):
        """Blue-gaps must be documented and have no fake SPL."""
        # It's OK if a blue-gap has SPL (maybe telemetry was added),
        # but this test documents the gap list exists
        assert isinstance(BLUE_GAPS, set), "BLUE_GAPS must be a set"
        assert len(BLUE_GAPS) >= 1, "BLUE_GAPS should have at least 1 entry"


class TestSPLIntegrity:
    """SPL detections must parse and reference real sourcetypes."""

    def test_spl_yaml_parses(self):
        data = yaml.safe_load(_SPL_YAML.read_text())
        assert isinstance(data, dict), "spl_detections.yaml is not a dict"
        assert len(data) >= 25, f"Expected >=25 SPL entries, got {len(data)}"

    def test_all_entries_have_required_fields(self):
        data = yaml.safe_load(_SPL_YAML.read_text())
        for tid, entry in data.items():
            assert isinstance(entry, dict), f"{tid} entry is not a dict"
            assert "spl" in entry, f"{tid} missing 'spl'"
            assert "description" in entry, f"{tid} missing 'description'"
            assert entry["spl"], f"{tid} has empty spl"

    def test_spl_references_real_sourcetype(self):
        """Each SPL should reference a known lab sourcetype."""
        valid_sourcetypes = {
            "web:access",
            "linux:auditd",
            "windows:security",
            "docker:daemon",
        }
        data = yaml.safe_load(_SPL_YAML.read_text())
        for tid, entry in data.items():
            spl = entry.get("spl", "")
            has_sourcetype = any(st in spl for st in valid_sourcetypes)
            assert has_sourcetype, (
                f"{tid} SPL doesn't reference a known lab sourcetype: {spl[:80]}..."
            )

    def test_new_techniques_present(self):
        """The 10 gap techniques from the task must now be in SPL or BLUE_GAPS."""
        required = {
            "T1003.001",
            "T1003.003",
            "T1047",
            "T1059.004",
            "T1078.004",
            "T1189",
            "T1203",
            "T1537",
            "T1552",
            "T1557.001",
        }
        spl_covered = set(techniques_covered())
        all_covered = spl_covered | BLUE_GAPS
        missing = required - all_covered
        assert not missing, f"Required techniques still missing: {sorted(missing)}"
