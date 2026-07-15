"""SecurityExecutor — the Stage-3 live-actuation bridge for the emergent
objective loop (DESIGN_EMERGENT_LAB_AGENT_V2 Δ1/Δ2, invariant D2).

Implements `portal.platform.agent.interfaces.Executor`: `execute(decision,
state) -> {"observation_delta", "oracle_result", "raw"}`. Wraps the existing
real actuation path (`lab.lab_dispatch`) and the named-oracle registry
(`oracles.verify_finding`) — no new offensive primitive is introduced (I2).

Ground-truth invariant (D2): the returned `observation_delta` is built ONLY
from the real dispatch result, the real oracle verdict, and live
`LabPerception` enumeration. `decision["expected_observation_delta"]` is the
model's *prediction* (used only by the Stage-2 dry-run simulator in
`loop.run_goal_engagement`) and is never read here — folding a prediction
into a "live" delta would be narration, not ground truth.
"""

from __future__ import annotations

from typing import Any

from portal.modules.security.core.perception import LabPerception, assert_in_lab

_TARGET_ARG_KEYS = ("target", "target_host", "host", "source_host")


def _extract_target(args: dict[str, Any]) -> str | None:
    for key in _TARGET_ARG_KEYS:
        val = args.get(key)
        if val:
            return str(val)
    return None


class SecurityExecutor:
    """Live executor for the emergent objective loop. Lab-scope guarded (I1)."""

    def __init__(self, perception: LabPerception | None = None, dry_run: bool = False):
        self._perception = perception
        self._dry_run = dry_run

    def execute(self, decision: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        from portal.modules.security.core import lab
        from portal.modules.security.core import oracles as oracle_mod

        tool = decision.get("tool") or decision.get("action") or ""
        args = dict(decision.get("args") or {})
        target = _extract_target(args)
        if target:
            assert_in_lab(target)  # I1: reject before any action leaves the box

        raw = lab.lab_dispatch(tool, args, dry_run=self._dry_run)

        oracle_id = decision.get("expected_oracle")
        oracle_result: bool | None = None
        delta: dict[str, Any] = {"last_tool": tool, "last_target": target}
        if oracle_id:
            observations = dict(state.get("observations") or {})
            verdict = oracle_mod.verify_finding(
                finding={"oracle": oracle_id}, lab_output=raw, observations=observations
            )
            oracle_result = verdict.verified
            delta[f"oracle:{oracle_id}"] = verdict.verified

        if self._perception is not None and target:
            p_delta = self._perception.enumerate([target])
            delta.update(p_delta.to_observation())

        return {"observation_delta": delta, "oracle_result": oracle_result, "raw": raw}
