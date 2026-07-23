"""Tests for multichain.consolidate — the "cooling"/triage decision across N
INDEPENDENT investigative chains.

Built 2026-07-22 (user: the RBP concept is a multi-model multi-chain analyst
taking known + unknown reads, hunting, then cooling to a decision — "we need a
human to look at this" or "we've detected a known bad"). The Council of
Agreement votes interpreters over ONE shared evidence pool; this consolidates
across chains that independently gathered DIFFERENT evidence, and makes the
ESCALATE ("needs human") decision a first-class outcome, not a fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from portal.modules.security.core.multichain import (
    ChainResult,
    consolidate,
    to_section_output,
)


def _c(model, verdict, techs=None, similar=None, sources=None):
    return ChainResult(
        model=model,
        verdict=verdict,
        technique_ids=techs or [],
        similar_to=similar or [],
        evidence_sources=sources or [],
    )


class TestConsolidate:
    def test_independent_convergence_is_auto_confirm(self):
        """>= quorum of independent chains reaching the same known technique is
        the strong KNOWN-BAD signal — auto-confirm."""
        chains = [
            _c("m1", "CONFIRMED", ["T1190"], sources=["web:access"]),
            _c("m2", "CONFIRMED", ["T1190"], sources=["ids:alert"]),
            _c("m3", "RULED_OUT", sources=["windows:security"]),
        ]
        res = consolidate(chains, quorum=0.5)
        assert res.decision == "AUTO_CONFIRM"
        assert res.verdict == "CONFIRMED"
        assert res.technique_ids == ["T1190"]

    def test_divergent_signal_is_escalate_not_confirm(self):
        """Independent chains each surfaced a DIFFERENT technique — real signal,
        no convergence. This is the strong ESCALATE ('needs human'), never a
        forced confirm or a silent dismiss."""
        chains = [
            _c("m1", "CONFIRMED", ["T1190"], sources=["web:access"]),
            _c("m2", "CONFIRMED", ["T1059"], sources=["linux:syslog"]),
            _c("m3", "ANOMALOUS_UNCLASSIFIED", similar=["T1505.003"], sources=["ids:alert"]),
        ]
        res = consolidate(chains, quorum=0.5)
        assert res.decision == "ESCALATE"
        assert res.verdict == "ANOMALOUS_UNCLASSIFIED"
        assert res.escalation_reason
        # near-miss neighbours carried forward for the human
        assert "T1505.003" in res.similar_to

    def test_all_independent_ruled_out_is_dismiss(self):
        chains = [
            _c("m1", "RULED_OUT", sources=["web:access"]),
            _c("m2", "RULED_OUT", sources=["ids:alert"]),
        ]
        res = consolidate(chains)
        assert res.decision == "DISMISS"
        assert res.verdict == "RULED_OUT"
        assert res.agreement == 1.0

    def test_no_conclusions_escalates_not_dismisses(self):
        """If no chain converged within budget, the investigation is
        incomplete — a live analyst can't be handed 'all clear'. Escalate."""
        chains = [_c("m1", "UNRESOLVED"), _c("m2", "UNRESOLVED")]
        res = consolidate(chains)
        assert res.decision == "ESCALATE"
        assert "did not complete" in res.rationale

    def test_mixed_benign_and_anomalous_escalates(self):
        """One chain uneasy (anomalous, no technique), others benign — a shared
        unease with no concrete claim escalates rather than silently dismissing."""
        chains = [
            _c("m1", "RULED_OUT", sources=["web:access"]),
            _c("m2", "ANOMALOUS_UNCLASSIFIED", sources=["ids:alert"]),
        ]
        res = consolidate(chains)
        assert res.decision == "ESCALATE"

    def test_evidence_diversity_counts_distinct_sources_across_chains(self):
        """The coverage win: consolidation reports how much of the telemetry
        surface the independent chains collectively touched — the structural
        answer to a single lead investigator's tunnel vision (HUNTER_MISS)."""
        chains = [
            _c("m1", "RULED_OUT", sources=["web:access", "ids:alert"]),
            _c("m2", "RULED_OUT", sources=["windows:security"]),
            _c("m3", "RULED_OUT", sources=["web:access"]),  # overlap w/ m1
        ]
        res = consolidate(chains)
        assert res.evidence_diversity == 3  # web:access, ids:alert, windows:security

    def test_quorum_threshold_respected(self):
        """A 2/3 vote clears quorum 0.5 but not 0.7."""
        chains = [
            _c("m1", "CONFIRMED", ["T1190"]),
            _c("m2", "CONFIRMED", ["T1190"]),
            _c("m3", "CONFIRMED", ["T1059"]),
        ]
        assert consolidate(chains, quorum=0.5).decision == "AUTO_CONFIRM"
        assert consolidate(chains, quorum=0.7).decision == "ESCALATE"

    def test_confirmed_carries_technique_to_section_output(self):
        res = consolidate([_c("m1", "CONFIRMED", ["T1190"]), _c("m2", "CONFIRMED", ["T1190"])])
        so = to_section_output(res)
        assert so.verdict == "CONFIRMED"
        assert so.technique_ids == ["T1190"]
        assert so.section == "consolidation"

    def test_escalate_section_output_carries_similar_as_grade(self):
        res = consolidate(
            [
                _c("m1", "CONFIRMED", ["T1190"]),
                _c("m2", "ANOMALOUS_UNCLASSIFIED", similar=["T1505.003"]),
                _c("m3", "CONFIRMED", ["T1059"]),
            ]
        )
        so = to_section_output(res)
        assert so.verdict == "ANOMALOUS_UNCLASSIFIED"
        assert so.match_grade == "SIMILAR"
        assert "T1505.003" in so.similar_to
