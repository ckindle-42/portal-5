"""Unit tests for Stage 1 self-index fidelity fix.

Covers two measurement bugs fixed in self_index.py:
1. `_read_coverage()` was blind to the chain-test result schema (only read matrix_results),
   silently picking a stale/wrong file and reporting 0 verified.
2. `_run_validator_json()` mis-parsed validate_system.py's multi-line --json output and treated
   any nonzero returncode (which validate_system.py returns whenever any check FAILs — expected,
   not a run failure) as an absent signal, hiding real validator_fail weaknesses.
"""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.scoring import classify_effort_tier
from portal.modules.security.core.self_index import (
    _coverage_from_chain,
    _coverage_from_matrix,
)


def _chain_entry(
    *,
    lab_success: bool = False,
    refused: bool = False,
    unique_coverage: float = 0.0,
    scenario: str = "s",
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "lab_success": lab_success,
        "refused": refused,
        "unique_coverage": unique_coverage,
    }


class TestCoverageFromChain:
    def test_counts_resolved_and_verified_strictly_from_lab_success(self) -> None:
        entries = [_chain_entry(lab_success=True) for _ in range(20)] + [
            _chain_entry(lab_success=False, refused=True),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.7),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.1),
            _chain_entry(lab_success=False, refused=False, unique_coverage=0.0),
        ]
        cov = _coverage_from_chain({"chain_tests": entries})
        assert cov is not None

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

    def test_none_when_no_chain_tests(self) -> None:
        assert _coverage_from_chain({"chain_tests": []}) is None
        assert _coverage_from_chain({}) is None

    def test_never_fabricates_verified_from_partial_success(self) -> None:
        """unique_coverage alone (honest_partial) must never count toward verified."""
        entries = [_chain_entry(lab_success=False, unique_coverage=0.9) for _ in range(5)]
        cov = _coverage_from_chain({"chain_tests": entries})
        assert cov is not None
        assert cov["verified"] == 0
        assert cov["tier_tally"]["honest_partial"] == 5


class TestCoverageFromMatrix:
    def test_extracts_flat_matrix_fields(self) -> None:
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
        assert cov is not None
        assert cov["resolved"] == 10
        assert cov["verified"] == 3

    def test_none_when_matrix_empty_or_zero(self) -> None:
        assert _coverage_from_matrix({"matrix_results": {}}) is None
        assert _coverage_from_matrix({"matrix_results": {"total_units": 0}}) is None
        assert _coverage_from_matrix({}) is None
