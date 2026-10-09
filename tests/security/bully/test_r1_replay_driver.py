"""R1.3: the product's default red side is replay. No red execution, no collection from lab
targets, and the recorded answer key never reaches the Episode.

Every external call is stubbed; nothing touches the network, Splunk, models or lab targets.
"""

from __future__ import annotations

import dataclasses

import pytest

from portal.modules.security.core import exec_chain
from portal.modules.security.core.bully import orchestrator


def _scenario_name() -> str:
    return next(iter(exec_chain.SCENARIOS))


@pytest.fixture
def stubs(monkeypatch):
    from portal.modules.security.core import blue
    from portal.modules.security.core.siem import capture_store

    calls: dict[str, int] = {"red": 0, "collect": 0, "replay": 0}

    def _no_red(*a, **k):
        calls["red"] += 1
        raise AssertionError("replay driver must never execute the red chain")

    def _no_collect(*a, **k):
        calls["collect"] += 1
        raise AssertionError("replay driver must never collect from lab targets")

    def _replay(path, **k):
        calls["replay"] += 1
        return {
            "ok": True,
            "episode_id": "ep-replay-test",
            "replay_start": 1000.0,
            "indexed_confirmed": True,
        }

    monkeypatch.setattr(exec_chain, "_run_chain_test", _no_red)
    monkeypatch.setattr(exec_chain, "_prepare_scenario", _no_red)
    from portal.modules.security.core import blue as blue_mod

    monkeypatch.setattr(blue_mod, "collect_and_ship_scenario_telemetry", _no_collect)
    monkeypatch.setattr(
        blue,
        "load_latest_red_capture",
        lambda scenario: ({"technique_ids": ["T1558.003"]}, "/recorded/capture.json"),
    )
    monkeypatch.setattr(capture_store, "replay_capture", _replay)
    monkeypatch.setattr(
        blue,
        "_run_blue_chain_test",
        lambda *a, **k: {
            "reported": True,
            "episode_id": k.get("episode_id"),
            "synthetic_fallback": False,
        },
    )
    return calls


def test_replay_builds_episode_without_red_or_collection(stubs):
    episode = orchestrator._replay_lab_driver({"scenario": _scenario_name()}, dry_run=False)
    assert stubs["red"] == 0
    assert stubs["collect"] == 0
    assert stubs["replay"] == 1
    assert episode.episode_id == "ep-replay-test"
    assert episode.red_status == "RED_LANDED"
    assert episode.telemetry_status == "TELEMETRY_OBSERVED"
    assert episode.used_synthetic is False
    assert episode.evidence_refs == ["/recorded/capture.json"]


def test_replay_dry_run_writes_nothing_and_stays_indeterminate(stubs):
    episode = orchestrator._replay_lab_driver({"scenario": _scenario_name()}, dry_run=True)
    assert stubs["replay"] == 0
    assert episode.used_synthetic is True
    assert episode.red_status == "RED_NOT_RUN"


def test_replay_without_recorded_exercise_is_an_honest_block(monkeypatch):
    from portal.modules.security.core import blue

    monkeypatch.setattr(blue, "load_latest_red_capture", lambda scenario: (None, None))
    with pytest.raises(orchestrator.HonestBlockedError, match="no replayable recorded exercise"):
        orchestrator._replay_lab_driver({"scenario": _scenario_name()}, dry_run=False)


def test_episode_carries_no_answer_key(stubs):
    episode = orchestrator._replay_lab_driver({"scenario": _scenario_name()}, dry_run=False)
    fields = {f.name for f in dataclasses.fields(episode)}
    assert not fields & {"technique_ids", "answer_key", "truth", "family", "implant_class"}
    assert "T1558.003" not in str(dataclasses.asdict(episode))


def test_iteration_default_is_replay(monkeypatch):
    """run_hunt_iteration falls back to the replay driver when no driver is injected."""
    import inspect

    src = inspect.getsource(orchestrator.run_hunt_iteration)
    assert "lab_driver = lab_driver or _replay_lab_driver" in src
    assert "_default_lab_driver" not in src
