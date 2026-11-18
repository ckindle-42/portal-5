"""Unit tests for Stage 1 self-legibility index — read-only enforcement, deterministic ranking."""

from __future__ import annotations

from typing import Any

import pytest

# ── Fixture: minimal index data ──────────────────────────────────────────────


# ── Test: build_self_index reads fixtures, never writes ───────────────────────


class TestBuildSelfIndex:
    def test_discipline_breadth_present(self) -> None:
        """Discipline breadth reads from PROMPTS — always present."""
        from portal.modules.security.core.self_index import _read_discipline_breadth

        disc = _read_discipline_breadth()
        assert disc["status"] == "present"
        assert len(disc["disciplines"]) > 0
        for _domain, ddata in disc["disciplines"].items():
            assert "red" in ddata
            assert "blue" in ddata

    def test_build_self_index_structure(self) -> None:
        """Full build_self_index returns all five top-level keys."""
        from portal.modules.security.core.self_index import build_self_index

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


# ── Test: rank_weaknesses — deterministic, transparent score ──────────────────


class TestRankWeaknesses:
    @pytest.fixture
    def sample_index(self) -> dict[str, Any]:
        return {
            "validator": {
                "status": "present",
                "passes": 24,
                "fails": 2,
                "checks": {
                    "A. python imports": {"status": "PASS", "detail": "ok"},
                    "B. pipeline assembles": {"status": "FAIL", "detail": "missing /v1/foo"},
                    "W. scenario-oracle": {"status": "FAIL", "detail": "3 issues"},
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

    def test_ranking_includes_failing_checks(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        failing = [w for w in weaknesses if w["kind"] == "failing_check"]
        assert len(failing) == 2
        assert failing[0]["score"] == 30

    def test_ranking_includes_heuristic_oracles(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

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

    def test_ranking_includes_zero_verified_classes(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        zero_verified = [w for w in weaknesses if w["kind"] == "class_zero_verified"]
        assert len(zero_verified) == 1
        assert zero_verified[0]["area"] == "class:sqli"
        assert zero_verified[0]["score"] == 25

    def test_ranking_includes_red_machines(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        red_machines = [w for w in weaknesses if w["kind"] == "machine_red_coverage"]
        assert len(red_machines) == 1
        assert red_machines[0]["area"] == "class:xss"
        assert red_machines[0]["score"] == 25

    def test_ranking_includes_discipline_gaps(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        red_only = [w for w in weaknesses if w["kind"] == "discipline_red_only"]
        absent = [w for w in weaknesses if w["kind"] == "discipline_absent"]
        assert len(red_only) == 1
        assert red_only[0]["area"] == "discipline:ad"
        assert len(absent) == 1
        assert absent[0]["area"] == "discipline:cloud"

    def test_ranking_includes_recurring_journal_failures(
        self, sample_index: dict[str, Any]
    ) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        journal_weak = [w for w in weaknesses if w["kind"] == "journal_recurring_failure"]
        assert len(journal_weak) == 1
        assert journal_weak[0]["score"] == 10
        assert "network timeout" in journal_weak[0]["evidence"]

    def test_ranking_includes_heuristic_only_scenarios(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        heuristic_scenarios = [w for w in weaknesses if w["kind"] == "scenario_heuristic_only"]
        assert len(heuristic_scenarios) == 1
        assert heuristic_scenarios[0]["area"] == "scenario:web_test"
        assert heuristic_scenarios[0]["score"] == 15

    def test_ranking_deterministic_ordering(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        w1 = rank_weaknesses(sample_index)
        w2 = rank_weaknesses(sample_index)
        assert w1 == w2

    def test_ranking_score_formula_inspectable(self, sample_index: dict[str, Any]) -> None:
        from portal.modules.security.core.self_index import rank_weaknesses

        weaknesses = rank_weaknesses(sample_index)
        for w in weaknesses:
            assert "score" in w
            assert "why" in w
            assert "area" in w
            assert "kind" in w
            assert "evidence" in w
            # Score must come from the documented _SCORE_RULES
            assert isinstance(w["score"], int)


# ── Helpers ───────────────────────────────────────────────────────────────────
