"""The report's screen and fitness views: the advance list, the confirm verdicts
and the dispositions (spec: docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import json

import pytest
import yaml

from tests.wfe import campaign as camp
from tests.wfe import decision
from tests.wfe import report as rep

WS_A = "auto-compliance"
WS_B = "auto-coding"
INC, CAND, OTHER = "inc:tag", "cand:tag", "other:tag"
SUITE = "compliance_agentic_full"
N_SCREEN = 10
N_TOTAL = 30


def _row(ws, arm, role, tid, repeat, tier, fail):
    return {
        "run_id": f"{ws}|{arm}|{SUITE}|{tid}|r{repeat}",
        "workspace": ws,
        "arm": arm,
        "model": arm,
        "arm_role": role,
        "suite": SUITE,
        "suite_path": str(rep.REPO / "tests/wfe/suites" / f"{SUITE}.jsonl"),
        "task_id": tid,
        "repeat": repeat,
        "tier": tier,
        "outcome": "FAIL" if fail else "PASS",
        "instrument": {"fingerprint": "fp1"},
    }


def _cell_rows(ws, arm, role, *, fail=False, screen_n=N_SCREEN, n=N_TOTAL):
    """A cell after a 10-task screen and a 30-task three-repeat confirm append.

    The screen's repeat-0 rows are reused as the confirm's repeat 0, so they keep
    tier="screen"; the append added only repeats 1..2 for those tasks."""
    out = []
    for i in range(n):
        tid = f"t{i:02d}"
        for r in range(1, 3) if i < screen_n else range(3):
            out.append(_row(ws, arm, role, tid, r, "confirm", fail))
        if i < screen_n:
            out.append(_row(ws, arm, role, tid, 0, "screen", fail))
    return out


def _campaign(tmp_path, monkeypatch, *, inc_fails=False, cand_fails=False, ws_b=False, name="c"):
    monkeypatch.setattr(rep, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    d = rep.CAMPAIGNS / name
    (d / "rows").mkdir(parents=True)
    (d / "preflight").mkdir(parents=True)
    rows = _cell_rows(WS_A, INC, "incumbent", fail=inc_fails) + _cell_rows(
        WS_A, CAND, "challenger", fail=cand_fails
    )
    if ws_b:
        rows += _cell_rows(WS_B, INC, "incumbent", fail=inc_fails) + _cell_rows(
            WS_B, OTHER, "challenger", fail=cand_fails
        )
    camp.save_manifest(
        d,
        {
            "campaign_id": name,
            "instrument": {"fingerprint": "fp1", "engine": "pipeline"},
            "env": {"fingerprint": "e"},
            "rows": rows,
        },
    )
    for r in rows:
        (d / "rows" / (camp.sha12(r["run_id"]) + ".json")).write_text(json.dumps(r))
    (d / "controls_receipts.jsonl").write_text(
        json.dumps({"where": "open", "suites": {f"{SUITE}.jsonl": "d1"}, "failures": []}) + "\n"
    )
    q = tmp_path / f"queue-{name}.yaml"
    q.write_text(
        "models:\n"
        f"  {INC}:\n    lineage: qwen3.8\n    available: true\n    intended: [{WS_A}]\n"
        f"  {CAND}:\n    lineage: granite\n    available: true\n    intended: [{WS_A}]\n"
        f"  {OTHER}:\n    lineage: other\n    available: true\n    intended: []\n"
    )
    return d, q


class TestFitnessView:
    def test_a_candidate_that_wins_every_task_is_better(self, tmp_path, monkeypatch):
        """The incumbent fails every task and the challenger passes every one."""
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        res = rep.fitness(d, q)
        (cell,) = [c for c in res["cells"] if c["candidate"] == CAND]
        assert (cell["verdict"], cell["wins"], cell["losses"]) == (decision.BETTER, N_TOTAL, 0)
        assert cell["n"] == N_TOTAL
        (disp,) = [x for x in res["dispositions"] if x["model"] == CAND]
        assert disp["disposition"] == "FOLD"

    def test_a_candidate_that_ties_is_not_separated(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        res = rep.fitness(d, q)
        (cell,) = [c for c in res["cells"] if c["candidate"] == CAND]
        assert cell["verdict"] == decision.NOT_SEPARATED
        (disp,) = [x for x in res["dispositions"] if x["model"] == CAND]
        # Intended, tied, and the only member of its lineage -> RETAIN_DIVERSITY.
        assert disp["disposition"] == "RETAIN_DIVERSITY"

    def test_a_model_with_no_intended_workspace_is_a_no_decision(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, ws_b=True)
        res = rep.fitness(d, q)
        (disp,) = [x for x in res["dispositions"] if x["model"] == OTHER]
        assert disp["disposition"] == "NO_DECISION"
        assert "intended" in disp["reason"]

    def test_fitness_records_the_instrument_it_was_computed_under(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        assert rep.fitness(d, q)["instrument"]["fingerprint"] == "fp1"


class TestScreenOut:
    def test_a_losing_candidate_in_an_intended_workspace_still_advances(
        self, tmp_path, monkeypatch
    ):
        """A screen DROP is a cost filter, not a decision: the model was queued
        for this lane, so only a full confirm may take it away."""
        d, q = _campaign(tmp_path, monkeypatch, cand_fails=True)
        res = rep.screen_out(d, q)
        assert res["advance"] == {WS_A: [CAND]}
        (cell,) = res["cells"]
        assert cell["verdict"] == decision.ADVANCE
        assert "intended workspace" in cell["reason"]

    def test_a_losing_candidate_outside_the_intended_workspaces_drops(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, cand_fails=True, ws_b=True)
        res = rep.screen_out(d, q)
        assert OTHER not in res["advance"].get(WS_B, [])
        (cell,) = [c for c in res["cells"] if c["candidate"] == OTHER]
        assert cell["verdict"] == decision.DROP
        assert cell["losses"] == N_SCREEN

    def test_a_winning_candidate_advances(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        (cell,) = rep.screen_out(d, q)["cells"]
        assert cell["verdict"] == decision.ADVANCE

    def test_the_advance_list_round_trips_into_the_plan_expansion(self, tmp_path, monkeypatch):
        """What --screen-out writes is what --advance reads."""
        d, q = _campaign(tmp_path, monkeypatch)
        adv = tmp_path / "advance.yaml"
        adv.write_text(yaml.safe_dump(rep.screen_out(d, q)["advance"], sort_keys=True))
        assert camp.load_advance(adv) == {WS_A: {CAND}}

    def test_below_the_screen_floor_nothing_is_dropped(self, tmp_path, monkeypatch):
        """A screen verdict needs at least eight compared tasks; below that the
        candidate advances however badly it did, because a sample that small
        decides nothing."""
        d, q = _campaign(tmp_path, monkeypatch, cand_fails=True, name="floor")
        rows = json.loads((d / "manifest.json").read_text())["rows"]
        keep = {"t00", "t01", "t02", "t03"}
        for r in rows:
            if r["tier"] == "screen" and r["task_id"] not in keep:
                r["tier"] = "confirm"
        camp.save_manifest(d, {**json.loads((d / "manifest.json").read_text()), "rows": rows})
        for r in rows:
            (d / "rows" / (camp.sha12(r["run_id"]) + ".json")).write_text(json.dumps(r))
        (cell,) = [c for c in rep.screen_out(d, q)["cells"] if c["candidate"] == CAND]
        assert cell["n"] == 4 < decision.SCREEN_MIN_TASKS
        assert cell["verdict"] == decision.ADVANCE
        assert "too few to drop" in cell["reason"]


class TestFitnessLedger:
    """Recording refuses anything that is not decision-grade."""

    def test_a_clean_pipeline_campaign_records_its_cells(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        led = tmp_path / "ledger.yaml"
        res = rep.record_ledger(d, q, led)
        (cell,) = [c for c in res["cells"] if c["model"] == CAND]
        assert cell["verdict"] == decision.BETTER
        assert cell["tier"] == "confirm"
        assert cell["campaign"] == "c"
        assert cell["instrument"] == "fp1"
        assert cell["receipts"] == {f"{SUITE}.jsonl": "d1"}
        assert cell["recorded_utc"]
        assert yaml.safe_load(led.read_text())["cells"] == res["cells"]

    def test_recording_twice_replaces_the_cell_rather_than_appending(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        led = tmp_path / "ledger.yaml"
        rep.record_ledger(d, q, led)
        res = rep.record_ledger(d, q, led)
        cells = yaml.safe_load(led.read_text())["cells"]
        assert len(cells) == len(res["cells"])
        assert len({(c["model"], c["workspace"]) for c in cells}) == len(cells)

    def test_a_direct_engine_campaign_is_refused(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        man = json.loads((d / "manifest.json").read_text())
        man["instrument"]["engine"] = "ollama"
        camp.save_manifest(d, man)
        with pytest.raises(SystemExit, match="not a pipeline-mode campaign"):
            rep.record_ledger(d, q, tmp_path / "ledger.yaml")

    def test_rows_measured_by_two_instruments_are_refused(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        man = json.loads((d / "manifest.json").read_text())
        man["rows"][0]["instrument"] = {"fingerprint": "fp2"}
        camp.save_manifest(d, man)
        (d / "rows" / (camp.sha12(man["rows"][0]["run_id"]) + ".json")).write_text(
            json.dumps(man["rows"][0])
        )
        with pytest.raises(SystemExit, match="one instrument fingerprint"):
            rep.record_ledger(d, q, tmp_path / "ledger.yaml")

    def test_a_failing_controls_receipt_is_refused(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        (d / "controls_receipts.jsonl").write_text(
            json.dumps({"where": "execute", "suites": {}, "failures": ["t1: echo passed"]}) + "\n"
        )
        with pytest.raises(SystemExit, match="record failures"):
            rep.record_ledger(d, q, tmp_path / "ledger.yaml")

    def test_a_campaign_with_no_controls_receipt_is_refused(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        (d / "controls_receipts.jsonl").unlink()
        with pytest.raises(SystemExit, match="controls gate never ran"):
            rep.record_ledger(d, q, tmp_path / "ledger.yaml")
