"""Check HP: a seat's ledger evidence must cite a pipeline campaign and a served
identity, and still describe what production serves (spec:
docs/WFE_ROOT_CAUSES_20261013.md, "Identity, the ledger and check HP").

Seats come from the repository's real config/portal.yaml and backends.yaml: an
earlier version of these tests wrote a {workspace: model} routing that
production does not have, so the check passed here and could never pass live.
Only the observation of a live engine is faked."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from portal.platform.inference.config import load_bench_workspaces_raw
from scripts.validation import wfe as hp

# The seat oracle covers production and bench routing.
_REPO = Path(hp.PORTAL).parent.parent
REAL = {
    **(yaml.safe_load(hp.PORTAL.read_text())["workspaces"]),
    **load_bench_workspaces_raw(_REPO),
}
WS = "auto-compliance"
SEAT = REAL[WS]["model_hint"]
CAND = "granite4.1:30b-ctx64k"


def _served(model="granite-4.1-30b-4bit", content="c-measured", backend="omlx-reasoning"):
    return {"backend": backend, "model": model, "content": content}


def _cell(campaign="c1", model=CAND, incumbent=SEAT, served=None):
    return {
        "model": model,
        "workspace": WS,
        "incumbent": incumbent,
        "campaign": campaign,
        "served": _served() if served is None else served,
        "incumbent_served": _served(model="Qwen3.8-27B-oQ4e-mtp", content="c-inc"),
    }


def _setup(
    tmp_path, monkeypatch, cells, engine="pipeline", now=("granite-4.1-30b-4bit", "c-measured")
):
    monkeypatch.setattr(hp, "LEDGER", tmp_path / "fitness_ledger.yaml")
    hp.LEDGER.write_text(yaml.safe_dump({"cells": cells}))
    monkeypatch.setattr(hp, "CAMPAIGNS", tmp_path / "campaigns")
    d = tmp_path / "campaigns" / "c1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"instrument": {"engine": engine}}))
    model_now, content_now = now
    monkeypatch.setattr(hp, "_served_today", lambda ws, m: model_now)
    monkeypatch.setattr(
        hp, "_content_today", lambda b, m: (content_now, "" if content_now else "down")
    )


def test_seats_are_the_models_production_seats():
    """Every routed workspace's seat is its model_hint: a model tag, never the
    backend-group list workspace_routing holds."""
    seats = hp._seats()
    routed = yaml.safe_load(hp.ROUTING.read_text())["workspace_routing"]
    assert len(seats) == len(routed) >= 50
    assert all(not s.startswith("[") for s in seats.values())
    assert all(seats[ws] == REAL[ws]["model_hint"] for ws in seats)
    assert seats[WS] == SEAT


def test_a_cell_that_defended_the_seat_covers_it(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()])
    status, _, subs = hp.check_wfe_fitness_ledger()
    assert subs[0]["status"] == "PASS" and subs[1]["status"] == "PASS"
    assert WS not in subs[2]["detail"]
    assert status == "WARN"  # the other seats still have no confirm cell


def test_a_cell_the_candidate_won_covers_its_new_seat(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell(model=SEAT, incumbent="previous:seat")])
    _, _, subs = hp.check_wfe_fitness_ledger()
    assert WS not in subs[2]["detail"]


def test_an_uncovered_seat_is_reported(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [])
    status, detail, subs = hp.check_wfe_fitness_ledger()
    assert status == "WARN" and subs[2]["status"] == "WARN"
    assert f"{len(hp._seats())} of {len(hp._seats())} seat(s)" in detail


def test_a_cell_citing_a_non_pipeline_campaign_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()], engine="ollama")
    status, _, subs = hp.check_wfe_fitness_ledger()
    assert status == "FAIL" and "ollama" in subs[0]["detail"]


def test_a_campaign_that_is_not_on_disk_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell(campaign="gone")])
    status, _, subs = hp.check_wfe_fitness_ledger()
    assert status == "FAIL" and "missing" in subs[0]["detail"]


def test_a_cell_without_a_served_identity_fails(tmp_path, monkeypatch):
    """Before P1R a cell whose identity lookup missed recorded the pipeline's git
    sha; that is not a served build and cannot be checked against production."""
    _setup(tmp_path, monkeypatch, [_cell(served="bb50fac84c7d44e81bf20082b99d96dd55089789")])
    status, _, subs = hp.check_wfe_fitness_ledger()
    assert status == "FAIL" and "no served identity" in subs[0]["detail"]


def test_a_current_cell_is_not_stale(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()])
    assert hp.check_wfe_fitness_ledger()[2][1]["status"] == "PASS"


def test_a_rebuild_under_the_same_name_is_stale(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()], now=("granite-4.1-30b-4bit", "c-rebuilt"))
    status, _, subs = hp.check_wfe_fitness_ledger()
    assert status == "WARN" and subs[1]["status"] == "WARN" and "rebuilt" in subs[1]["detail"]


def test_a_different_served_model_is_stale(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()], now=("granite-4.1-30b-8bit", "c-measured"))
    _, _, subs = hp.check_wfe_fitness_ledger()
    assert (
        subs[1]["status"] == "WARN"
        and "production now serves granite-4.1-30b-8bit" in subs[1]["detail"]
    )


def test_an_unobservable_build_is_a_warning_not_a_pass(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, [_cell()], now=("granite-4.1-30b-4bit", ""))
    _, _, subs = hp.check_wfe_fitness_ledger()
    assert subs[1]["status"] == "WARN" and "cannot observe" in subs[1]["detail"]


def test_hp_reads_the_ledger_path_from_the_environment(tmp_path):
    """The rig and the live acceptance record into a scratch ledger and point HP at it."""
    import os
    import subprocess
    import sys

    led = tmp_path / "elsewhere.yaml"
    out = subprocess.run(
        [sys.executable, "-c", "from scripts.validation import wfe; print(wfe.LEDGER)"],
        cwd=hp.REPO_ROOT,
        env={**os.environ, "WFE_FITNESS_LEDGER": str(led)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == str(led)
