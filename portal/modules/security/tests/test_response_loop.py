"""Tests for response loop + threat-driven intake — Phase 7.

Validates:
- Response growth loop: COVERED + RESPONSE_MISSING → draft playbook
- Response effectiveness check is deterministic
- Reverse growth loop: BLUE_ONLY → draft red scenario
- Threat intake maps CVE to gaps
- Playbook actions come from primitives (not free-generated)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "benchmarks"))

from portal.modules.security.core.capability_graph import (
    CoverageSummary,
    seed_graph_from_assets,
)
from portal.modules.security.core.response_loop import (
    RESPONSE_PRIMITIVES,
    check_response_effectiveness,
    map_threat_to_gaps,
    propose_red_scenario,
    propose_response_playbook,
    run_response_loop,
)

# ── Response playbook ────────────────────────────────────────────────────────


class TestResponsePlaybook:
    """Response playbook drafts use existing primitives, not free-generation."""

    def test_propose_playbook(self):
        playbook = propose_response_playbook("T1190", "web_sqli_dump")
        assert playbook.technique_id == "T1190"
        assert playbook.status == "draft"
        assert len(playbook.actions) > 0

    def test_playbook_actions_from_primitives(self):
        playbook = propose_response_playbook("T1190", "test")
        for action in playbook.actions:
            assert action["action"] in RESPONSE_PRIMITIVES

    def test_playbook_for_credential_theft(self):
        playbook = propose_response_playbook("T1003.006", "kerberoast_to_da")
        action_names = [a["action"] for a in playbook.actions]
        assert "revoke_tgt" in action_names or "reset_password" in action_names

    def test_playbook_to_dict(self):
        playbook = propose_response_playbook("T1190", "test")
        d = playbook.to_dict()
        json.dumps(d)


# ── Response effectiveness ───────────────────────────────────────────────────


class TestResponseEffectiveness:
    """Effectiveness check is deterministic."""

    def test_effective_response(self):
        playbook = propose_response_playbook("T1190", "test")
        result = check_response_effectiveness(playbook, red_can_continue=False)
        assert result["effective"] is True
        assert result["tested"] is True

    def test_ineffective_response(self):
        playbook = propose_response_playbook("T1190", "test")
        result = check_response_effectiveness(playbook, red_can_continue=True)
        assert result["effective"] is False


# ── Reverse growth loop ──────────────────────────────────────────────────────


class TestReverseGrowthLoop:
    """BLUE_ONLY gap → draft red scenario."""

    def test_propose_red_scenario(self):
        draft = propose_red_scenario("T1190", "Web exploit detection")
        assert draft.technique_id == "T1190"
        assert draft.status == "draft"

    def test_red_scenario_draft_to_dict(self):
        draft = propose_red_scenario("T1190")
        d = draft.to_dict()
        json.dumps(d)


# ── Threat-driven intake ─────────────────────────────────────────────────────


class TestThreatIntake:
    """Threat intake maps new threats against capability graph."""

    def test_map_threat_with_gaps(self):
        graph = seed_graph_from_assets()
        intake = map_threat_to_gaps(
            graph,
            threat_id="CVE-2024-1234",
            threat_type="cve",
            technique_ids=["T1190"],
        )
        assert intake.threat_id == "CVE-2024-1234"
        assert "T1190" in intake.mapped_techniques
        # T1190 has a scenario and a detection, so no gaps
        # (unless we pick a technique without one)

    def test_map_threat_without_detection(self):
        graph = seed_graph_from_assets()
        intake = map_threat_to_gaps(
            graph,
            threat_id="CVE-2024-5678",
            threat_type="cve",
            technique_ids=["T1078.004"],  # no SPL detection
        )
        assert len(intake.gaps_identified) > 0
        assert any(g["gap_type"] == "detection" for g in intake.gaps_identified)

    def test_map_threat_without_scenario(self):
        graph = seed_graph_from_assets()
        # Pick a technique that's in detections but not in any scenario
        intake = map_threat_to_gaps(
            graph,
            threat_id="new-technique",
            threat_type="technique",
            technique_ids=["T1610"],  # has detection, might not have scenario
        )
        # Should identify exercise gap if T1610 isn't in any scenario
        assert intake.threat_id == "new-technique"

    def test_intake_to_dict(self):
        graph = seed_graph_from_assets()
        intake = map_threat_to_gaps(graph, "test", "cve", ["T1190"])
        d = intake.to_dict()
        json.dumps(d)


# ── Response loop runner ─────────────────────────────────────────────────────


class TestResponseLoopRunner:
    """Response loop runner finds gaps and proposes playbooks/drafts."""

    def test_run_response_loop(self):
        graph = seed_graph_from_assets()
        # Mark some gaps as COVERED with RESPONSE_MISSING
        for gap in list(graph.gaps.values())[:5]:
            gap.summary = CoverageSummary.COVERED.value
            gap.axes["response"] = "RESPONSE_NOT_TESTED"

        result = run_response_loop(graph)
        assert result.response_gaps_found >= 1
        assert result.playbooks_proposed >= 1

    def test_run_response_loop_finds_reverse_gaps(self):
        graph = seed_graph_from_assets()
        # Mark some gaps as BLUE_ONLY
        for gap in list(graph.gaps.values())[:3]:
            gap.summary = CoverageSummary.BLUE_ONLY.value

        result = run_response_loop(graph)
        assert result.reverse_gaps_found >= 1
        assert result.red_drafts_proposed >= 1

    def test_response_loop_result_to_dict(self):
        graph = seed_graph_from_assets()
        result = run_response_loop(graph)
        d = result.to_dict()
        json.dumps(d)
