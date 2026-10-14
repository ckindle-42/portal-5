"""Check HP: a seat's ledger evidence must cite a pipeline campaign and still
describe what production serves (spec: docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import json

import yaml

from scripts.validation import wfe as hp

WS, MODEL = "auto-compliance", "inc:tag"


def _ledger(tmp_path, monkeypatch, cells):
    monkeypatch.setattr(hp, "LEDGER", tmp_path / "fitness_ledger.yaml")
    hp.LEDGER.write_text(yaml.safe_dump({"cells": cells}))
    return hp.LEDGER


def _routing(tmp_path, monkeypatch, seats):
    monkeypatch.setattr(hp, "ROUTING", tmp_path / "backends.yaml")
    hp.ROUTING.write_text(yaml.safe_dump({"workspace_routing": seats}))


def _campaign(tmp_path, monkeypatch, cid, engine):
    monkeypatch.setattr(hp, "CAMPAIGNS", tmp_path / "campaigns")
    d = tmp_path / "campaigns" / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"instrument": {"engine": engine}}))


def _cell(campaign="c1", served="Qwen3.8-27B-oQ4e-mtp"):
    return {"model": MODEL, "workspace": WS, "campaign": campaign, "served": served}


def test_a_pipeline_cell_that_still_matches_production_passes(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, [_cell()])
    _campaign(tmp_path, monkeypatch, "c1", "pipeline")
    _routing(tmp_path, monkeypatch, {WS: MODEL})
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: "Qwen3.8-27B-oQ4e-mtp")
    status, detail, _ = hp.check_wfe_fitness_ledger()
    assert status == "PASS", detail


def test_a_cell_citing_a_non_pipeline_campaign_fails(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, [_cell()])
    _campaign(tmp_path, monkeypatch, "c1", "ollama")
    _routing(tmp_path, monkeypatch, {WS: MODEL})
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: None)
    status, detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "FAIL"
    assert "non-pipeline" in detail
    assert subs[0]["status"] == "FAIL" and "ollama" in subs[0]["detail"]


def test_a_campaign_that_is_not_on_disk_fails(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, [_cell(campaign="gone")])
    monkeypatch.setattr(hp, "CAMPAIGNS", tmp_path / "campaigns")
    _routing(tmp_path, monkeypatch, {WS: MODEL})
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: None)
    status, _detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "FAIL"
    assert subs[0]["status"] == "FAIL" and "missing" in subs[0]["detail"]


def test_a_seat_whose_served_build_moved_is_stale(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, [_cell(served="Qwen3.8-27B-oQ4e-mtp")])
    _campaign(tmp_path, monkeypatch, "c1", "pipeline")
    _routing(tmp_path, monkeypatch, {WS: MODEL})
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: "Qwen3.8-27B-oQ8-mtp")
    status, detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "WARN" and "STALE" in detail
    assert subs[1]["status"] == "WARN" and "production now serves" in subs[1]["detail"]


def test_a_seat_with_no_confirm_cell_warns(tmp_path, monkeypatch):
    _ledger(tmp_path, monkeypatch, [])
    monkeypatch.setattr(hp, "CAMPAIGNS", tmp_path / "campaigns")
    _routing(tmp_path, monkeypatch, {WS: MODEL, "auto-coding": "other:tag"})
    status, detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "WARN" and "no confirm cell" in detail
    assert subs[2]["status"] == "WARN"
    assert "2 of 2" in subs[2]["detail"]


def test_a_seat_covered_by_its_own_model_does_not_warn(tmp_path, monkeypatch):
    """The seat is covered only by a cell for the model seated there."""
    _ledger(tmp_path, monkeypatch, [_cell()])
    _campaign(tmp_path, monkeypatch, "c1", "pipeline")
    _routing(tmp_path, monkeypatch, {WS: MODEL, "auto-coding": "other:tag"})
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: "Qwen3.8-27B-oQ4e-mtp")
    status, detail, subs = hp.check_wfe_fitness_ledger()
    assert subs[2]["status"] == "WARN" and "1 of 2" in subs[2]["detail"]
    assert subs[0]["status"] == "PASS" and subs[1]["status"] == "PASS"


def test_a_missing_ledger_file_is_no_cells_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(hp, "LEDGER", tmp_path / "absent.yaml")
    monkeypatch.setattr(hp, "CAMPAIGNS", tmp_path / "campaigns")
    _routing(tmp_path, monkeypatch, {WS: MODEL})
    status, _detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "WARN" and subs[0]["status"] == "PASS"
