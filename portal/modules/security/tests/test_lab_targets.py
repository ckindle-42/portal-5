"""Unit tests for lab targets catalog (Phase 0b)."""

from __future__ import annotations


class TestChallengeClasses:
    def test_ability_port_imports(self) -> None:
        from portal.modules.security.core.ability_port import ability_coverage

        cov = ability_coverage()
        assert cov["challenge_classes"] >= 40
        assert cov["ptai_probes_ported"] >= 20
        assert cov["vulhub_families_mapped"] >= 7
