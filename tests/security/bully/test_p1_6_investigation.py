"""P1.6 -- investigation arm over blue_orchestrate runners (live Episode).

Per the P1 task file: "grounding gate drops uncited claims; budget/stall
caps honored; adapter consumes a live Episode fixture. Feeds I2."
`_run_three_section` is mocked (it is a full model-calling multi-round
loop -- out of hermetic-unit scope per the testing rules); everything this
module itself does (grounding gate application, hand-off handling, kwarg
forwarding) runs for real against the mock's output.
"""

from __future__ import annotations

from unittest.mock import patch

from portal.modules.security.core.bully import investigation
from portal.modules.security.core.episode import Episode


def _live_episode() -> Episode:
    return Episode(
        episode_id="ep-20260101T000000Z-scn-abcd1234",
        scenario="lateral-movement-wmi",
        target_host="host-1",
        started_at=0.0,
        red_status="RED_LANDED",
        telemetry_status="TELEMETRY_INDEXED",
        detection_status="DETECTION_CONFIRMED",
    )


class _FakeOrchestrationResult:
    def __init__(self, verdict, technique_ids, evidence, reasoning="because", match_grade="EXACT"):
        self.verdict = verdict
        self.technique_ids = technique_ids
        self.evidence = evidence
        self.reasoning = reasoning
        self.match_grade = match_grade


def test_grounding_gate_drops_uncited_claims():
    # T1021.002 is mentioned in the gathered evidence; T9999 (invented) is not.
    fake_result = _FakeOrchestrationResult(
        verdict="CONFIRMED",
        technique_ids=["T1021.002", "T9999"],
        evidence=["wmic process call create observed on host-1, technique T1021.002"],
    )
    with patch(
        "portal.modules.security.core.blue_orchestrate._run_three_section", return_value=fake_result
    ):
        result = investigation.run_arm(
            _live_episode(), models={"tool": "t", "reasoning": "r", "expert": "e"}
        )

    assert "T9999" in result.dropped_technique_ids
    assert "T9999" not in result.grounded_technique_ids


def test_budget_and_stall_caps_are_forwarded_to_the_section_runner():
    fake_result = _FakeOrchestrationResult(verdict="CONFIRMED", technique_ids=[], evidence=[])
    with patch(
        "portal.modules.security.core.blue_orchestrate._run_three_section", return_value=fake_result
    ) as mocked:
        investigation.run_arm(
            _live_episode(),
            models={"tool": "t", "reasoning": "r", "expert": "e"},
            max_rounds=4,
            wall_clock_s=120.0,
        )
    _, kwargs = mocked.call_args
    assert kwargs["max_rounds"] == 4
    assert kwargs["wall_clock_s"] == 120.0


def test_adapter_consumes_a_live_episode_fixture():
    ep = _live_episode()
    fake_result = _FakeOrchestrationResult(verdict="CONFIRMED", technique_ids=[], evidence=[])
    with patch(
        "portal.modules.security.core.blue_orchestrate._run_three_section", return_value=fake_result
    ) as mocked:
        result = investigation.run_arm(ep, models={"tool": "t", "reasoning": "r", "expert": "e"})
    called_episode = mocked.call_args[0][0]
    assert called_episode is ep  # the live Episode object itself, not a replay DTO
    assert result.verdict == "CONFIRMED"


def test_midchain_handoff_returns_unresolved_never_fabricates_a_verdict():
    from portal.modules.security.core.blue_orchestrate import HunterHandoff

    handoff = HunterHandoff.__new__(HunterHandoff)  # bypass __init__ -- opaque marker for this test
    with patch(
        "portal.modules.security.core.blue_orchestrate._run_three_section", return_value=handoff
    ):
        result = investigation.run_arm(
            _live_episode(), models={"tool": "t", "reasoning": "r", "expert": "e"}
        )
    assert result.verdict == "UNRESOLVED"
    assert result.technique_ids == ()
