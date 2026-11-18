"""Offline escalation: fakes only. No live dispatch, Telegram, or git push."""

from __future__ import annotations

from typing import Any

import pytest

from portal.modules.orchestration.escalate import (
    LaneChanges,
    classify_block,
    decide,
    dispatch_kind,
    escalation_enabled,
)


def _receipt(status: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "purpose": "exercise escalation",
        "reason": extra.pop("reason", ""),
        "steps": extra.pop("steps", []),
    }
    payload.update(extra)
    return payload


def _failed_step(stdout: str = "boom\n") -> dict[str, Any]:
    return {
        "id": "run",
        "argv": ["scripts/step.py"],
        "state": "failed",
        "reason": "step exited 1",
        "stdout_tail": stdout,
        "stderr_tail": "",
    }


def test_flag_defaults_off() -> None:
    assert escalation_enabled({}) is False
    assert escalation_enabled({"escalation": {"enabled": False}}) is False
    assert escalation_enabled({"escalation": {"enabled": True}}) is True


def test_classify_matches_the_four_triggers_and_skips_a_cancel() -> None:
    setup = "CANARY demo: SETUP (1 setup row(s) of 1)\n"
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step(setup)])) == "canary_setup"
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step("HARNESS_ERROR\n")])) == (
        "harness_error"
    )
    assert classify_block(_receipt("BLOCKED", steps=[_failed_step()])) == "step_failure"
    trip = _failed_step()
    trip["state"] = "stopped"
    trip["memory_trip"] = {"reason": "fixture"}
    assert classify_block(
        _receipt("STOPPED", reason="memory safety trip: fixture", steps=[trip])
    ) == ("memory_trip")
    assert classify_block(_receipt("CANCELLED", reason="cancelled by operator")) is None
    assert (
        classify_block(_receipt("BLOCKED", reason="cancelled by operator", steps=[_failed_step()]))
        is None
    )
    stopped = _failed_step("BLOCKED: preflight\n")
    stopped["state"] = "stopped"
    stopped["reason"] = "output matched stop marker"
    assert (
        classify_block(_receipt("STOPPED", reason="output matched stop marker", steps=[stopped]))
        is None
    )


def test_security_jobs_use_the_security_kind() -> None:
    assert dispatch_kind({"id": "compliance-recapture", "purpose": "refresh", "steps": []}) == (
        "security"
    )
    assert dispatch_kind({"id": "job-a", "purpose": "detection pack", "steps": []}) == "security"
    assert (
        dispatch_kind(
            {
                "id": "job-a",
                "purpose": "run task",
                "steps": [{"id": "scan", "argv": ["tests/security.py"]}],
            }
        )
        == "security"
    )
    assert (
        dispatch_kind({"id": "job-a", "purpose": "count rows", "steps": [{"id": "one"}]}) == "code"
    )


def test_allowlist_holds_portal_and_merges_wfe() -> None:
    assert decide(LaneChanges(("tests/wfe/test_ok.py",), (), ())).status == "merge"
    assert decide(LaneChanges(("tests/wfe/plans/x.yaml",), (), ())).status == "merge"
    assert decide(LaneChanges(("config/arm_jobs/job.yaml",), (), ())).status == "merge"
    held = decide(LaneChanges(("portal/modules/orchestration/queue.py",), (), ()))
    assert held.status == "hold"
    assert "portal/" in held.detail
    assert decide(LaneChanges(("scripts/step.py",), (), ())).status == "hold"
    assert decide(LaneChanges(("Dockerfile.pipeline",), (), ())).status == "hold"
    assert decide(LaneChanges((), ("tests/wfe/test_ok.py",), ())).status == "uncommitted"
    assert decide(LaneChanges((), (), ())).status == "empty"


def test_escalation_canary_uses_a_throwaway_campaign_id() -> None:
    from portal.modules.orchestration.escalate import _throwaway_campaign

    argv = ["scripts/wfe_campaign.sh", "realuse_reruns_20261030b", "--plan", "p.yaml", "--canary"]
    out = _throwaway_campaign(argv, "portal-esc-Ab_9x")
    assert out[1] == "realuse_reruns_20261030b_portalescab9x"
    assert out[2:] == argv[2:]
    assert argv[1] == "realuse_reruns_20261030b"
    assert _throwaway_campaign(["other.sh", "x", "--canary"], "t") == ["other.sh", "x", "--canary"]


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("## RESULT\n\nAPPROVE\n\n## FINDINGS\n\nnone\n", "approve"),
        ("## RESULT: APPROVE\n", "approve"),
        ("## RESULT\n**APPROVE** — diff is sound\n", "approve"),
        ("## RESULT\ndone\n## RESULT\nAPPROVE\n", "approve"),
        ("## RESULT\ndone\n", "hold"),
    ],
)
def test_oracle_verdict_reads_the_first_word(text: str, verdict: str) -> None:
    from portal.modules.orchestration.escalate import _parse_oracle

    assert _parse_oracle(text, set()).verdict == verdict
