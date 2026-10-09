"""R1.3 defect D1: a dry-run product iteration must record RED_NOT_RUN, never RED_EXECUTION_FAILED.

The chain functions are stubbed so the test exercises only the episode builder in
`orchestrator._default_lab_driver`, with no network, no models and no lab.
"""

from __future__ import annotations

import pytest

from portal.modules.security.core import exec_chain
from portal.modules.security.core.bully import orchestrator


def _stub_chain(monkeypatch: pytest.MonkeyPatch, *, lab_success: bool) -> None:
    scenario = next(iter(exec_chain.SCENARIOS.values()))
    monkeypatch.setattr(
        exec_chain,
        "_prepare_scenario",
        lambda *a, **k: {"ready": True, "host": scenario.get("target_host")},
    )
    # The dry-run chain result carries no lab_success key at all (exec_chain.py:3586).
    monkeypatch.setattr(
        exec_chain,
        "_run_chain_test",
        lambda *a, **k: (
            {"model": "m", "chain_depth": 0, "outcome": "dry_run", "mode": "synthetic"}
            if k.get("dry_run")
            else {"lab_success": lab_success}
        ),
    )
    from portal.modules.security.core import blue

    monkeypatch.setattr(
        blue,
        "collect_and_ship_scenario_telemetry",
        lambda *a, **k: (None, False, None),
    )
    monkeypatch.setattr(
        blue,
        "_run_blue_chain_test",
        lambda *a, **k: {"reported": False, "episode_id": k.get("episode_id") or "x"},
    )


@pytest.mark.parametrize(
    ("dry_run", "lab_success", "expected"),
    [
        (True, False, "RED_NOT_RUN"),
        (False, True, "RED_LANDED"),
        (False, False, "RED_EXECUTION_FAILED"),
    ],
)
def test_red_status_follows_execution_mode(monkeypatch, dry_run, lab_success, expected):
    _stub_chain(monkeypatch, lab_success=lab_success)
    name = next(iter(exec_chain.SCENARIOS))
    episode = orchestrator._default_lab_driver({"scenario": name}, dry_run=dry_run)
    assert episode.red_status == expected
