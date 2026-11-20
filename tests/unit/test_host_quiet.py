from __future__ import annotations

import yaml

from scripts import host_quiet


def _quiet_snapshot(**overrides):
    snapshot = {
        "other_heavy_processes": [],
        "headroom_gib": 32.0,
        "minimum_headroom_gib": 1.5,
        "maximum_pytest_processes": 5,
        "ollama_residents": [],
        "omlx_residents": [],
        "configured_resident_models": [],
    }
    snapshot.update(overrides)
    return snapshot


def test_blockers_report_idle_residents_by_engine():
    snapshot = _quiet_snapshot(
        ollama_residents=[{"name": "ollama-extra", "size_gib": 4.0}],
        omlx_residents=[{"name": "omlx-extra", "estimated_size_gib": 3.0}],
    )

    reasons = host_quiet.blockers(snapshot)

    assert len(reasons) == 1
    assert "idle model residents hold 7.0 GiB" in reasons[0]
    assert "ollama/ollama-extra 4.00 GiB" in reasons[0]
    assert "omlx/omlx-extra 3.00 GiB" in reasons[0]
    assert host_quiet.is_transient_blocker(reasons[0])


def test_preferred_resident_and_small_total_do_not_block():
    snapshot = _quiet_snapshot(
        configured_resident_models=["preferred-model"],
        ollama_residents=[
            {"name": "preferred-model", "size_gib": 20.0},
            {"name": "small-ollama", "size_gib": 0.4},
        ],
        omlx_residents=[{"name": "small-omlx", "size_gib": 0.5}],
    )

    assert host_quiet.blockers(snapshot) == []


def test_preferred_residents_are_resolved_from_config(tmp_path):
    (tmp_path / "config").mkdir()
    backends = {
        "defaults": {"preferred_residents": ["auto-daily"]},
        "backends": [{"aliases": {"preferred-hint": "preferred-omlx"}}],
    }
    portal = {"workspaces": {"auto-daily": {"model_hint": "preferred-hint"}}}
    (tmp_path / "config" / "backends.yaml").write_text(yaml.safe_dump(backends))
    (tmp_path / "config" / "portal.yaml").write_text(yaml.safe_dump(portal))

    assert host_quiet._configured_resident_models(tmp_path) == {
        "preferred-hint",
        "preferred-omlx",
    }


def test_clear_uses_pipeline_reclaim_endpoint_and_rechecks(monkeypatch, capsys):
    before = _quiet_snapshot(
        ollama_residents=[{"name": "ollama-extra", "size_gib": 0.25}],
    )
    after = _quiet_snapshot()
    snapshots = iter([before, after])
    calls = []

    monkeypatch.setattr(host_quiet, "capture_snapshot", lambda *_args: next(snapshots))
    monkeypatch.setattr(
        host_quiet,
        "_json_request",
        lambda url, **kwargs: calls.append((url, kwargs)) or {"unloads": []},
    )

    result = host_quiet.main(
        ["--clear", "--pipeline-url", "http://pipeline:9099", "--api-key", "secret"]
    )

    assert result == 0
    assert calls[0][0] == "http://pipeline:9099/admin/reclaim-idle"
    assert calls[0][1]["method"] == "POST"
    assert calls[0][1]["payload"]["need_gib"] == 0.25
    assert "ollama-extra" in capsys.readouterr().out
