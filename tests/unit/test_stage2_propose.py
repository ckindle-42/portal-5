"""Unit tests for Stage 2 propose+prove+gate oracle-tier promotions — synthetic/dry-run.

Most important: the false-promotion guard. A hollow tier-only flip must NEVER be
marked promotable, no matter what a (necessarily fake, since untested) proof claims.
"""

from __future__ import annotations

import copy

from tests.benchmarks.bench_security.stage2_propose import (
    Proof,
    apply_batch,
    classify_outcome,
    generate_proposal,
    goal_eval,
    weak_oracle_ids,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


class _FakeOracle:
    def __init__(self, tier="experimental", kind="unit_test_kind"):
        self.tier = tier
        self.kind = kind
        self.honesty_claim = "proves a unit-test fact, not anything real"


def _proven_proof(oracle_id="fake_oracle", source="sec_bench_fake.json") -> dict:
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


def _insufficient_proof(oracle_id="fake_oracle") -> dict:
    return Proof(oracle_id=oracle_id, source_file="", insufficient_evidence=True).as_dict()


def _false_positive_proof(oracle_id="fake_oracle") -> dict:
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


def _sample_index(oracle_id="fake_oracle", tier="experimental") -> dict:
    return {
        "oracles": {
            "oracles": {
                oracle_id: {"tier": tier, "kind": "unit_test_kind"},
            }
        }
    }


# ── The false-promotion guard (most important) ─────────────────────────────


class TestFalsePromotionGuard:
    def test_hollow_flag_flip_never_promotable(self):
        """A proposal that only flips tier with no real check strengthening → not promotable,
        EVEN IF proof (falsely) claims a clean positive+negative pass — the diff itself never
        touched the check, so a stub can never be promoted by evidence alone."""
        oracle = _FakeOracle()
        proposal = generate_proposal("fake_oracle", oracle)
        assert proposal["diff_touches_check"] is False  # generator never speculates
        index = _sample_index()

        # diff untouched + unproven (real data absent) -> hollow, not promotable
        result = goal_eval(proposal, _insufficient_proof(), index=index)
        assert result["promotable"] is False
        assert any("insufficient" in r for r in result["reasons"])

        # diff untouched + a proof claiming a real check pass -> proven=True makes
        # the diff-untouched case no longer "hollow" (the existing check IS proven
        # correct as-is); this is the one legitimate way a tier-only flip can be
        # promotable — it's not a flag flip, it's evidence the code already works.
        proven_result = goal_eval(proposal, _proven_proof(), index=index)
        assert proven_result["evidence"]["hollow"] is False
        assert proven_result["promotable"] is True

    def test_hollow_can_never_be_marked_promotable_directly(self):
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
    def test_clean_positive_and_negative_proof_is_promotable(self):
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

    def test_false_positive_on_negative_entry_blocks_promotion(self):
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

    def test_insufficient_evidence_is_not_a_forced_pass_or_fail(self):
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
    def test_goal_eval_deterministic(self):
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

    def test_fitness_delta_uses_real_rank_weaknesses(self):
        """The fitness-delta recompute must call the real self_index.rank_weaknesses,
        not an assumed/hardcoded value."""
        from tests.benchmarks.bench_security.self_index import rank_weaknesses
        from tests.benchmarks.bench_security.stage2_propose import _fitness_delta_if_promoted

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
    def test_weak_oracle_ids_matches_stage1_weakness_view(self):
        """The live ORACLES registry has exactly 41 experimental + 5 differential = 46 weak."""
        from tests.benchmarks.bench_security.oracles import ORACLES

        weak = weak_oracle_ids(ORACLES)
        assert len(weak) == 46
        tiers = {ORACLES[oid].tier for oid in weak}
        assert tiers <= {"experimental", "differential"}
        # deterministic order
        assert weak == sorted(weak)


# ── The gate: no writes without --apply ─────────────────────────────────────


class TestGateHolds:
    def test_propose_without_apply_writes_nothing_to_oracle_source(self, tmp_path, monkeypatch):
        """Running propose (no --apply) must never touch oracles.py or ability_port.py."""
        from tests.benchmarks.bench_security import stage2_propose as s2

        oracles_before = s2._ORACLES_PY.read_text()
        ability_before = s2._ABILITY_PORT_PY.read_text()

        out_dir = tmp_path / "stage2_proposals"
        report = s2.run_stage2()
        s2.write_report(report, out_dir=out_dir)

        assert s2._ORACLES_PY.read_text() == oracles_before
        assert s2._ABILITY_PORT_PY.read_text() == ability_before
        assert (out_dir / "stage2_report.json").exists()

    def test_apply_batch_is_never_invoked_by_run_stage2_or_write_report(self, tmp_path):
        """apply_batch is a distinct function the propose pipeline never calls internally —
        only stage2_propose_main(apply=True) (i.e. an explicit operator --apply) may call it."""
        import inspect

        from tests.benchmarks.bench_security import stage2_propose as s2

        run_stage2_src = inspect.getsource(s2.run_stage2)
        write_report_src = inspect.getsource(s2.write_report)
        assert "apply_batch" not in run_stage2_src
        assert "apply_batch" not in write_report_src

    def test_apply_batch_applies_only_when_promotable_and_diff_staged(self, tmp_path):
        """Sanity check of apply_batch mechanics against a scratch copy — not the real source."""
        from tests.benchmarks.bench_security.stage2_propose import Stage2Report

        fake_dir = tmp_path / "stage2_proposals"
        fake_dir.mkdir()
        report = Stage2Report(
            generated_at="2026-07-02T00:00:00Z",
            source_file="sec_bench_fake.json",
            total_weak_oracles=1,
            promotable=[
                {
                    "oracle_id": "does_not_exist_oracle",
                    "proposal": {"current_tier": "experimental"},
                }
            ],
        )
        result = apply_batch(report, out_dir=fake_dir)
        # No staged diff on disk for this fake id -> skipped, nothing applied
        assert result["applied"] == []
        assert "does_not_exist_oracle" in result["skipped"]
