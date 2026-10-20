"""Cause C3: rows and segments record what measured them, by content."""

from __future__ import annotations

import json

import pytest

from tests.wfe import campaign, report


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    for p in campaign.FINGERPRINTED_CONFIG:
        (tmp_path / p).write_text("a: 1\n")
    (tmp_path / "tests/wfe/results").mkdir(parents=True)
    (tmp_path / "tests/wfe/runner.py").write_text("x = 1\n")
    monkeypatch.setattr(campaign, "REPO", tmp_path)
    return tmp_path


def _fp() -> str:
    return campaign.instrument_fingerprint()["fingerprint"]


def test_fingerprint_names_its_inputs():
    fp = campaign.instrument_fingerprint()
    assert set(fp) == {
        "commit",
        "harness",
        "config",
        "portal_tree",
        "deployed",
        "services",
        "engine",
        "fingerprint",
    }


def test_result_writes_do_not_change_the_instrument(fake_repo):
    before = _fp()
    (fake_repo / "tests/wfe/results/row.json").write_text("{}")
    assert _fp() == before


def test_source_content_changes_the_instrument_even_when_untracked(fake_repo):
    before = _fp()
    (fake_repo / "tests/wfe/new_helper.py").write_text("y = 2\n")
    after_add = _fp()
    (fake_repo / "tests/wfe/new_helper.py").write_text("y = 3\n")
    assert len({before, after_add, _fp()}) == 3


def test_config_change_changes_the_instrument(fake_repo):
    before = _fp()
    (fake_repo / "config/portal.yaml").write_text("a: 2\n")
    assert _fp() != before


def test_dirty_instrument_refuses_to_gate(monkeypatch):
    monkeypatch.setattr(campaign, "instrument_dirty", lambda: ["tests/wfe/runner.py"])
    monkeypatch.delenv("WFE_ALLOW_DIRTY_INSTRUMENT", raising=False)
    with pytest.raises(SystemExit, match="uncommitted"):
        campaign.gate_controls([], "open")
    monkeypatch.setenv("WFE_ALLOW_DIRTY_INSTRUMENT", "1")
    assert campaign.gate_controls([], "open")["failures"] == []


def test_preflight_blocks_a_deployed_build_that_is_not_head(monkeypatch):
    model = sorted(campaign.backend_catalog())[0]
    monkeypatch.setattr(campaign, "deployed_build", lambda: "unknown")
    monkeypatch.setattr(
        campaign,
        "chat",
        lambda ws, m, tools=True, harness=None, **k: {
            "served": {"model": campaign.seat_primary(ws, model)}
        },
    )
    v = campaign.preflight_pipeline(["auto-coding"], model)
    assert v["verdict"] == "REVIEW" and "deployed pipeline build" in v["findings"][0]


def test_deployed_matches_only_a_real_commit_with_heads_tree():
    assert not campaign.deployed_matches("unknown")
    assert not campaign.deployed_matches("unreachable")
    head = campaign._git("rev-parse", "HEAD").strip()
    assert campaign.deployed_matches(head)


def test_manifest_and_append_segments_record_the_instrument(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    d = campaign.open_campaign("c", plan, [], append=False)
    assert (
        json.loads((d / "manifest.json").read_text())["instrument"]
        == campaign.instrument_fingerprint()
    )
    campaign.open_campaign("c", plan, [], append=True)
    m = json.loads((d / "manifest.json").read_text())
    assert m["appends"][-1]["instrument"] == campaign.instrument_fingerprint()


def _row(fp):
    return {"instrument": {"fingerprint": fp}} if fp else {}


def test_report_refuses_rows_from_two_instruments():
    with pytest.raises(SystemExit, match="MIXED INSTRUMENT"):
        report._instrument_check([_row("a"), _row("b")], allow_mixed=False)


def test_report_refuses_new_rows_pooled_with_pre_provenance_rows():
    with pytest.raises(SystemExit, match="legacy"):
        report._instrument_check([_row("a"), _row(None)], allow_mixed=False)


def test_one_instrument_pools_and_allow_mixed_only_warns():
    assert report._instrument_check([_row("a"), _row("a")], allow_mixed=False) == []
    (w,) = report._instrument_check([_row("a"), _row("b")], allow_mixed=True)
    assert "not sound" in w


@pytest.mark.asyncio
async def test_pipeline_health_reports_its_build(monkeypatch):
    from portal.platform.inference.router import handlers

    class Reg:
        health_checked = True

        def list_healthy_backends(self):
            return [1]

        def list_backends(self):
            return [1]

    monkeypatch.setattr(handlers, "registry", Reg())
    monkeypatch.setenv("PORTAL_BUILD_SHA", "abc1234")
    assert (await handlers.health())["build_sha"] == "abc1234"


# ── the frozen baseline is enforced, with no cache to clear ──────────────────


def _open(tmp_path, monkeypatch, rows=()):
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    return campaign.open_campaign("c", plan, list(rows), append=False), plan


def test_observation_is_fresh_every_call(fake_repo):
    before = campaign.instrument_fingerprint()["fingerprint"]
    (fake_repo / "config/portal.yaml").write_text("a: 3\n")
    assert campaign.instrument_fingerprint()["fingerprint"] != before


def test_execution_refuses_a_campaign_whose_instrument_changed(fake_repo, tmp_path, monkeypatch):
    d, _ = _open(tmp_path, monkeypatch)
    campaign.gate_execution(d)
    (fake_repo / "tests/wfe/runner.py").write_text("x = 2\n")
    with pytest.raises(SystemExit, match="instrument drift in \\['harness'\\]"):
        campaign.gate_execution(d)


def test_append_refuses_a_changed_instrument(fake_repo, tmp_path, monkeypatch):
    _, plan = _open(tmp_path, monkeypatch)
    (fake_repo / "config/backends.yaml").write_text("b: 1\n")
    with pytest.raises(SystemExit, match="append: instrument drift"):
        campaign.open_campaign("c", plan, [], append=True)


def test_deployed_build_change_is_drift(fake_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    build = {"sha": "aaaaaaa"}
    monkeypatch.setattr(campaign, "deployed_build", lambda: build["sha"])
    d, _ = _open(tmp_path, monkeypatch)
    build["sha"] = "bbbbbbb"
    assert "deployed" in campaign.instrument_drift(campaign.load_manifest(d))


def test_drift_after_a_row_quarantines_it_and_stops_the_arm(fake_repo, tmp_path, monkeypatch):
    r = {"run_id": "w|a|s|t|r0", "arm": "a", "state": "PENDING"}
    d, _ = _open(tmp_path, monkeypatch, [r])
    m = campaign.load_manifest(d)
    row = {"outcome": "PASS", "notes": ""}
    assert campaign.arm_stop_reason("a", row, d, m, m["rows"][0]) is None
    (fake_repo / "config/portal.yaml").write_text("a: 9\n")
    why = campaign.arm_stop_reason("a", row, d, m, m["rows"][0])
    assert why and "config" in why
    saved = json.loads(campaign._row_path(d, r["run_id"]).read_text())
    assert saved["outcome"] == "BLOCKED" and saved["notes"].startswith("INSTRUMENT DRIFT")
    assert campaign.load_manifest(d)["rows"][0]["state"] == "BLOCKED"


# ── every participating service proves its build (root-fix Part 2c) ─────────


def test_service_findings_name_every_reason_a_service_is_untrusted(monkeypatch):
    head = campaign._git("rev-parse", "HEAD").strip()
    svcs = {
        "ok": {"build_sha": head, "build_dirty": 0},
        "docker": {"build_sha": head, "build_dirty": -1},
        "down": {"build_sha": "unreachable", "build_dirty": -1, "error": "refused"},
        "stale": {"build_sha": "0" * 40, "build_dirty": 0},
        "dirty": {"build_sha": head, "build_dirty": 3},
    }
    got = campaign.service_findings(svcs)
    assert len(got) == 3 and any("down service unreachable" in g for g in got)
    assert any(g.startswith("stale service runs build") for g in got) and any(
        "dirty service" in g for g in got
    )


def test_preflight_blocks_on_a_stale_service(monkeypatch):
    monkeypatch.setattr(
        campaign, "deployed_services", lambda: {"memory": {"build_sha": "0" * 40, "build_dirty": 0}}
    )
    monkeypatch.setattr(campaign, "chat", lambda *a, **k: {"served": {"model": "x"}})
    monkeypatch.setattr(campaign, "seat_primary", lambda ws, m: "x")
    monkeypatch.setattr(campaign, "backend_catalog", lambda: {"m"})
    res = campaign.preflight_pipeline(["w"], "m")
    assert any("memory service runs build" in f for f in res["findings"]) and res["verdict"] != "OK"


def test_a_service_rebuilt_mid_campaign_is_drift(fake_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "ENGINE", "pipeline")
    monkeypatch.setattr(campaign, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(campaign, "deployed_build", lambda: "a" * 40)
    svc = {"rag": {"build_sha": "a" * 40, "build_dirty": 0}}
    monkeypatch.setattr(campaign, "deployed_services", lambda: {k: dict(v) for k, v in svc.items()})
    plan = tmp_path / "plan.yaml"
    plan.write_text("workloads: {}\n")
    d = campaign.open_campaign("c", plan, [], append=False)
    assert campaign.instrument_drift(campaign.load_manifest(d)) is None
    svc["rag"]["build_sha"] = "b" * 40
    assert "services" in campaign.instrument_drift(campaign.load_manifest(d))
