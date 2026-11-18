"""Unit tests for Stage 2 propose+prove+gate oracle-tier promotions — synthetic/dry-run.

Most important: the false-promotion guard. A hollow tier-only flip must NEVER be
marked promotable, no matter what a (necessarily fake, since untested) proof claims.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from portal.modules.security.core.stage2_propose import (
    Proof,
    classify_outcome,
    goal_eval,
    weak_oracle_ids,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _proven_proof(
    oracle_id: str = "fake_oracle", source: str = "sec_bench_fake.json"
) -> dict[str, Any]:
    return Proof(
        oracle_id=oracle_id,
        source_file=source,
        positive_tested=3,
        positive_passed=3,
        negative_tested=3,
        negative_passed=0,
        insufficient_evidence=False,
        evidence_detail="3/3 positive verified, 0/3 negative false-verified",
        entries_examined=6,
    ).as_dict()


def _insufficient_proof(oracle_id: str = "fake_oracle") -> dict[str, Any]:
    return Proof(oracle_id=oracle_id, source_file="", insufficient_evidence=True).as_dict()


def _false_positive_proof(oracle_id: str = "fake_oracle") -> dict[str, Any]:
    return Proof(
        oracle_id=oracle_id,
        source_file="sec_bench_fake.json",
        positive_tested=3,
        positive_passed=3,
        negative_tested=3,
        negative_passed=1,  # false positive on a benign entry
        insufficient_evidence=False,
        entries_examined=6,
    ).as_dict()


def _sample_index(oracle_id: str = "fake_oracle", tier: str = "experimental") -> dict[str, Any]:
    return {
        "oracles": {
            "oracles": {
                oracle_id: {"tier": tier, "kind": "unit_test_kind"},
            }
        }
    }


# ── The false-promotion guard (most important) ─────────────────────────────


class TestFalsePromotionGuard:
    def test_hollow_can_never_be_marked_promotable_directly(self) -> None:
        """Construct the exact hollow shape (diff_touches_check False, proven False) and assert
        goal_eval's own hollow flag makes promotable impossible."""
        proposal = {
            "oracle_id": "fake_oracle",
            "scope": ["fake_oracle"],
            "current_tier": "experimental",
            "diff_touches_check": False,
        }
        proof = {
            "insufficient_evidence": False,
            "positive_tested": 0,
            "positive_passed": 0,
            "negative_tested": 0,
            "negative_passed": 0,
        }
        result = goal_eval(proposal, proof, index=_sample_index())
        assert result["evidence"]["hollow"] is True
        assert result["promotable"] is False


# ── Proven promotions ───────────────────────────────────────────────────────


class TestProvenPromotion:
    def test_clean_positive_and_negative_proof_is_promotable(self) -> None:
        proposal = {
            "oracle_id": "fake_oracle",
            "scope": ["fake_oracle"],
            "current_tier": "experimental",
            "diff_touches_check": True,  # check was strengthened as part of this proposal
        }
        proof = _proven_proof()
        result = goal_eval(proposal, proof, index=_sample_index())
        assert result["promotable"] is True
        assert result["reasons"] == []

    def test_false_positive_on_negative_entry_blocks_promotion(self) -> None:
        proposal = {
            "oracle_id": "fake_oracle",
            "scope": ["fake_oracle"],
            "current_tier": "experimental",
            "diff_touches_check": True,
        }
        proof = _false_positive_proof()
        result = goal_eval(proposal, proof, index=_sample_index())
        assert result["promotable"] is False
        assert any("false positive" in r for r in result["reasons"])

    def test_insufficient_evidence_is_not_a_forced_pass_or_fail(self) -> None:
        proposal = {
            "oracle_id": "fake_oracle",
            "scope": ["fake_oracle"],
            "current_tier": "experimental",
            "diff_touches_check": True,
        }
        proof = _insufficient_proof()
        result = goal_eval(proposal, proof, index=_sample_index())
        assert result["promotable"] is False
        outcome = classify_outcome(result, proof)
        assert outcome == "not-promotable-yet (insufficient evidence)"


# ── goal_eval is deterministic ──────────────────────────────────────────────


class TestDeterminism:
    def test_goal_eval_deterministic(self) -> None:
        proposal = {
            "oracle_id": "fake_oracle",
            "scope": ["fake_oracle"],
            "current_tier": "experimental",
            "diff_touches_check": True,
        }
        proof = _proven_proof()
        index = _sample_index()
        r1 = goal_eval(proposal, proof, index=index)
        r2 = goal_eval(proposal, copy.deepcopy(proof), index=copy.deepcopy(index))
        assert r1 == r2

    def test_fitness_delta_uses_real_rank_weaknesses(self) -> None:
        """The fitness-delta recompute must call the real self_index.rank_weaknesses,
        not an assumed/hardcoded value."""
        from portal.modules.security.core.self_index import rank_weaknesses
        from portal.modules.security.core.stage2_propose import _fitness_delta_if_promoted

        index = _sample_index(tier="experimental")
        weaknesses_before = rank_weaknesses(index)
        before_entry = [w for w in weaknesses_before if w["area"] == "oracle:fake_oracle"]
        assert before_entry and before_entry[0]["score"] > 0

        fd = _fitness_delta_if_promoted("fake_oracle", index)
        assert fd["before"] == before_entry[0]["score"]
        assert fd["after"] == 0  # stable tier scores 0
        assert fd["delta"] == fd["before"]


# ── Weak oracle identification (the real 46) ────────────────────────────────


class TestWeakOracleIds:
    def test_weak_oracle_ids_matches_stage1_weakness_view(self) -> None:
        """The live ORACLES registry has exactly 45 experimental + 5 differential = 50 weak.

        45 experimental = 41 pre-existing + 4 terminal-state objective oracles
        (objective_oracles.py, Slice 2.2 of TASK_EMERGENT_SLICE2_TRAJECTORY_SCORING_V1).
        """
        from portal.modules.security.core import (
            objective_oracles,  # noqa: F401 — registration side effect
        )
        from portal.modules.security.core.oracles import ORACLES

        weak = weak_oracle_ids(ORACLES)
        assert len(weak) == 50
        tiers = {ORACLES[oid].tier for oid in weak}
        assert tiers <= {"experimental", "differential"}
        # deterministic order
        assert weak == sorted(weak)


# ── The gate: no writes without --apply ─────────────────────────────────────


class TestValidatorRecursionGuard:
    def test_check_stage2_propose_integrity_skips_when_nested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """check AB calls run_stage2() -> build_self_index() -> shells out to
        validate_system.py --json, which runs check AB again. Without a guard this
        forks unboundedly (the exact bug check Y already had to guard against —
        found live as a 145+-process fork chain). Assert the guard fires and no
        subprocess is spawned in the nested case."""
        import subprocess

        import scripts.validation.security_bench as vs

        monkeypatch.setenv("PORTAL5_SELF_INDEX_NESTED", "1")

        def _fail_if_called(*_a: object, **_kw: object) -> None:
            raise AssertionError("subprocess.run must not be called when nested")

        monkeypatch.setattr(subprocess, "run", _fail_if_called)

        status, _detail, _subs = vs.check_stage2_propose_integrity()
        assert status == "SKIP"
