"""The report's screen and fitness views: the advance list, the confirm verdicts
and the dispositions (spec: docs/WFE_ROOT_CAUSES_20261013.md)."""

from __future__ import annotations

import json
import sys

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


def _ident(ws, model):
    """What an arm's preflight observes and every row re-observes: one per pair."""
    return {"backend": "omlx-reasoning", "model": f"served-{model}", "content": f"c-{ws}-{model}"}


def _row(ws, arm, role, tid, repeat, tier, fail):
    model = arm.split("@")[0]
    return {
        "run_id": f"{ws}|{arm}|{SUITE}|{tid}|r{repeat}",
        "workspace": ws,
        "arm": arm,
        "model": model,
        "identity": _ident(ws, model),
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


def _campaign(
    tmp_path, monkeypatch, *, inc_fails=False, cand_fails=False, ws_b=False, name="c", cand=CAND
):
    monkeypatch.setattr(rep, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    d = rep.CAMPAIGNS / name
    (d / "rows").mkdir(parents=True)
    (d / "preflight").mkdir(parents=True)
    rows = _cell_rows(WS_A, INC, "incumbent", fail=inc_fails) + _cell_rows(
        WS_A, cand, "challenger", fail=cand_fails
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
            "identity_map": {f"{r['workspace']}|{r['model']}": r["identity"] for r in rows},
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


class TestVariantArmAgainstTheQueue:
    """A variant arm id is `<tag>@<label>-<digest>`; the queue is keyed by the bare tag.
    The screen used to miss the intended override and the fitness view lost the cells."""

    VARIANT = f"{CAND}@card-abcd1234"

    def test_a_losing_variant_arm_in_an_intended_workspace_still_advances(
        self, tmp_path, monkeypatch
    ):
        d, q = _campaign(tmp_path, monkeypatch, cand_fails=True, cand=self.VARIANT)
        res = rep.screen_out(d, q)
        assert res["advance"] == {WS_A: [self.VARIANT]}

    def test_a_variant_arm_is_dispositioned_under_its_model_tag(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True, cand=self.VARIANT)
        res = rep.fitness(d, q)
        (disp,) = [x for x in res["dispositions"] if x["model"] == CAND]
        assert disp["disposition"] == "FOLD"
        assert disp["cells"] == {WS_A: decision.BETTER}


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

    def test_a_cell_names_its_incumbent_and_both_served_identities(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        (cell,) = [
            c for c in rep.record_ledger(d, q, tmp_path / "l.yaml")["cells"] if c["model"] == CAND
        ]
        assert cell["incumbent"] == INC
        assert cell["served"] == _ident(WS_A, CAND)
        assert cell["incumbent_served"] == _ident(WS_A, INC)

    def test_a_card_arm_records_its_model_tags_identity(self, tmp_path, monkeypatch):
        """The identity map is keyed by model tag. Keyed by the arm id, a card arm
        missed it and the cell recorded the pipeline's git sha as its served build."""
        arm = f"{CAND}@card-c1832928"
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True, cand=arm)
        (cell,) = [
            c for c in rep.record_ledger(d, q, tmp_path / "l.yaml")["cells"] if c["arm"] == arm
        ]
        assert cell["model"] == CAND
        assert cell["served"] == _ident(WS_A, CAND)

    def test_a_campaign_whose_identities_were_never_frozen_is_refused(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch)
        man = json.loads((d / "manifest.json").read_text())
        del man["identity_map"]
        camp.save_manifest(d, man)
        with pytest.raises(SystemExit, match="no frozen identities"):
            rep.record_ledger(d, q, tmp_path / "ledger.yaml")

    def test_recording_keeps_the_ledger_header(self, tmp_path, monkeypatch):
        d, q = _campaign(tmp_path, monkeypatch, inc_fails=True)
        led = tmp_path / "ledger.yaml"
        rep.record_ledger(d, q, led)
        assert led.read_text().startswith(rep.LEDGER_HEADER)


class TestFitnessMap:
    """The P5-B1 view: dispose() from every decision-grade ledger cell, not one
    campaign's, so a model whose lanes were confirmed in different campaigns
    still reaches a terminal verdict."""

    def _fixtures(self, tmp_path, models, cells):
        q = tmp_path / "queue.yaml"
        q.write_text(yaml.safe_dump({"models": models}))
        led = tmp_path / "ledger.yaml"
        led.write_text(yaml.safe_dump({"cells": cells}))
        return q, led

    @staticmethod
    def _cell(model, ws, verdict, campaign):
        return {
            "model": model,
            "workspace": ws,
            "verdict": verdict,
            "campaign": campaign,
            "tier": "confirm",
        }

    def test_cells_from_two_campaigns_merge_into_one_terminal_verdict(self, tmp_path):
        models = {"gran:tag": {"lineage": "gran", "available": True, "intended": [WS_A, WS_B]}}
        cells = [
            self._cell("gran:tag", WS_A, decision.NOT_SEPARATED, "c-compliance"),
            self._cell("gran:tag", WS_B, decision.BETTER, "c-documents"),
        ]
        q, led = self._fixtures(tmp_path, models, cells)
        res = rep.fitness_map(q, led)
        (d,) = res["dispositions"]
        assert d["cells"] == {WS_A: decision.NOT_SEPARATED, WS_B: decision.BETTER}
        assert d["campaigns"] == {WS_A: "c-compliance", WS_B: "c-documents"}
        assert d["disposition"] == "FOLD"
        assert f"'{WS_B}'" in d["reason"]

    def test_a_tied_model_sharing_its_lineage_is_redundant(self, tmp_path):
        models = {
            "a:tag": {"lineage": "ln", "available": True, "intended": [WS_A]},
            "b:tag": {"lineage": "ln", "available": True, "intended": [WS_B]},
        }
        cells = [self._cell("a:tag", WS_A, decision.NOT_SEPARATED, "c1")]
        q, led = self._fixtures(tmp_path, models, cells)
        (d,) = [x for x in rep.fitness_map(q, led)["dispositions"] if x["model"] == "a:tag"]
        assert d["disposition"] == "REDUNDANT"

    def test_a_tied_sole_lineage_retains_diversity(self, tmp_path):
        models = {"solo:tag": {"lineage": "ln", "available": True, "intended": [WS_A]}}
        cells = [self._cell("solo:tag", WS_A, decision.NOT_SEPARATED, "c1")]
        q, led = self._fixtures(tmp_path, models, cells)
        (d,) = rep.fitness_map(q, led)["dispositions"]
        assert d["disposition"] == "RETAIN_DIVERSITY"

    def test_a_queued_model_with_no_cells_disposes_from_the_queue(self, tmp_path):
        models = {
            "want:tag": {"lineage": "w", "available": True, "intended": [WS_A]},
            "blank:tag": {"lineage": "b", "available": True, "intended": []},
        }
        q, led = self._fixtures(tmp_path, models, [])
        res = rep.fitness_map(q, led)
        by = {d["model"]: d for d in res["dispositions"]}
        assert by["want:tag"]["disposition"] == "NO_DECISION"
        assert f"'{WS_A}'" in by["want:tag"]["reason"]
        assert by["blank:tag"]["disposition"] == "NO_DECISION"
        assert "no intended workspace" in by["blank:tag"]["reason"]

    def test_a_ledger_cell_the_queue_does_not_name_still_surfaces(self, tmp_path):
        models = {"kept:tag": {"lineage": "k", "available": True, "intended": [WS_A]}}
        cells = [self._cell("stray:tag", WS_A, decision.BETTER, "c1")]
        q, led = self._fixtures(tmp_path, models, cells)
        res = rep.fitness_map(q, led)
        by = {d["model"]: d for d in res["dispositions"]}
        assert by["stray:tag"]["queued"] is False
        assert "no intended workspace" in by["stray:tag"]["reason"]

    def test_fitness_map_flag_prints_the_map_without_writing(self, tmp_path, monkeypatch, capsys):
        models = {"gran:tag": {"lineage": "gran", "available": True, "intended": [WS_A, WS_B]}}
        cells = [
            self._cell("gran:tag", WS_A, decision.NOT_SEPARATED, "c1"),
            self._cell("gran:tag", WS_B, decision.BETTER, "c2"),
        ]
        q, led = self._fixtures(tmp_path, models, cells)
        map_doc = tmp_path / "WFE_FITNESS_MAP.md"
        monkeypatch.setattr(rep, "MAP_DOC", map_doc)
        monkeypatch.setattr(
            sys,
            "argv",
            ["report", "--fitness-map", "--queue", str(q), "--ledger", str(led)],
        )
        assert rep.main() == 0
        out = capsys.readouterr().out
        assert "| model | intended |" in out
        assert "FOLD" in out
        assert not map_doc.exists()

    def test_write_map_writes_the_markdown(self, tmp_path, monkeypatch, capsys):
        models = {"gran:tag": {"lineage": "gran", "available": True, "intended": [WS_A]}}
        cells = [self._cell("gran:tag", WS_A, decision.NOT_SEPARATED, "c1")]
        q, led = self._fixtures(tmp_path, models, cells)
        map_doc = tmp_path / "WFE_FITNESS_MAP.md"
        monkeypatch.setattr(rep, "MAP_DOC", map_doc)
        monkeypatch.setattr(
            sys,
            "argv",
            ["report", "--write-map", "--queue", str(q), "--ledger", str(led)],
        )
        assert rep.main() == 0
        text = map_doc.read_text()
        assert text.startswith("# WFE fitness map")
        assert "gran:tag" in text and "RETAIN_DIVERSITY" in text
        assert f"map: {map_doc}" in capsys.readouterr().out
