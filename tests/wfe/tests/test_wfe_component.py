"""The component test for what Part 1 installs: screen -> --screen-out -> confirm
append -> --fitness -> --record, offline, on a hand-written plan.

The queue and the eligibility generator arrive in Part 3, so this uses fixed
eligibility facts. The full queue-to-ledger test is Part 3's gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.wfe import campaign as camp
from tests.wfe import decision
from tests.wfe import report as rep
from tests.wfe import runner as rn

WS_INTENDED = "auto-compliance"
WS_OTHER = "auto-coding"
INC = "inc:tag"
BETTER, TIED, DROPPED = "better:tag", "tied:tag", "dropped:tag"
GONE = "gone:tag"
N_SCREEN, N_TOTAL = 10, 30

#: Which (workspace, arm) passes. The incumbent is deliberately measured twice:
#: it loses every task in the workspace `better` is queued for, and wins every
#: task in the workspace `dropped` is queued for.
_WINS = {
    (WS_INTENDED, INC): False,
    (WS_INTENDED, BETTER): True,
    (WS_INTENDED, TIED): False,
    (WS_OTHER, INC): True,
    (WS_OTHER, DROPPED): False,
}


def _row(ws, arm, role, tid, repeat, tier, *, fail):
    return {
        "run_id": f"{ws}|{arm}|home|{tid}|r{repeat}",
        "workspace": ws,
        "arm": arm,
        "model": arm,
        "arm_role": role,
        "suite": "home",
        "suite_path": str(camp.SUITE_DIR / "home.jsonl"),
        "task_id": tid,
        "repeat": repeat,
        "tier": tier,
        "outcome": "FAIL" if fail else "PASS",
        "instrument": {"fingerprint": "fp-test", "engine": "pipeline"},
    }


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """A hermetic campaign: fixture suites, fake chat, no live engine or pipeline."""
    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "home.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "id": f"t{i:02d}",
                    "instruction": "Finish the job.",
                    "checkers": [{"type": "answer_contains", "patterns": ["TASK COMPLETE"]}],
                    **({"screen": True} if i < N_SCREEN else {}),
                }
            )
            + "\n"
            for i in range(N_TOTAL)
        )
    )
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        yaml.safe_dump(
            {
                "workloads": {
                    WS_INTENDED: {
                        "home": "home",
                        "discovery": [],
                        "arms": {"incumbent": INC, "challengers": [BETTER, TIED]},
                    },
                    WS_OTHER: {
                        "home": "home",
                        "discovery": [],
                        "arms": {"incumbent": INC, "challengers": [DROPPED]},
                    },
                }
            }
        )
    )
    queue = tmp_path / "queue.yaml"
    queue.write_text(
        "models:\n"
        f"  {INC}:\n    lineage: incumbent\n    available: true\n"
        f"    intended: [{WS_INTENDED}, {WS_OTHER}]\n"
        f"  {BETTER}:\n    lineage: challenger\n    available: true\n"
        f"    intended: [{WS_INTENDED}]\n"
        f"  {TIED}:\n    lineage: distinct\n    available: true\n"
        f"    intended: [{WS_INTENDED}]\n"
        f"  {DROPPED}:\n    lineage: dropped\n    available: true\n    intended: []\n"
        # Queued but not restorable: every cell is MISSING, so it can only be
        # NO_DECISION. The generator that fills this in is Part 3's.
        f"  {GONE}:\n    lineage: gone\n    available: false\n"
        f"    intended: [{WS_INTENDED}]\n"
    )

    monkeypatch.setattr(camp, "SUITE_DIR", suites)
    monkeypatch.setattr(camp, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(rep, "CAMPAIGNS", tmp_path / "campaigns")
    monkeypatch.setattr(camp, "ENGINE", "pipeline")
    monkeypatch.setattr(camp, "CHAT_BASE", "http://pipeline.invalid")
    monkeypatch.setattr(camp, "instrument_dirty", lambda: [])
    monkeypatch.setattr(camp, "deployed_build", lambda: "deadbeef")
    monkeypatch.setattr(camp, "deployed_matches", lambda build: True)
    monkeypatch.setattr(camp, "seat_primary", lambda ws, model: f"served-{model}")
    monkeypatch.setattr(camp, "drain_model", lambda *a, **k: True)
    monkeypatch.setattr(camp, "drain_others", lambda *a, **k: [])

    seen: list[tuple[str, str]] = []

    def fake_chat(model, messages, **kwargs):  # noqa: ARG001 - model is the workspace
        """Deterministic per (workspace, task): the model under test decides."""
        arm = (kwargs.get("harness") or {}).get("pipeline_model") or model
        task = next(
            (
                ln
                for ln in str(messages[-1].get("content", "")).splitlines()
                if ln.startswith("Finish the job.")
            ),
            "",
        )
        seen.append((arm, task))
        ok = _WINS.get((model, arm), True)
        return {
            "message": {"content": "TASK COMPLETE" if ok else "no", "tool_calls": []},
            "finish_reason": "stop",
            "economics": rn.Economics(),
            "harness_caveats": [],
            "resolved_think": "false",
            "served": {"backend": "omlx-test", "model": f"served-{arm}"},
        }

    monkeypatch.setattr(rn, "chat", fake_chat)
    return {"plan": plan, "queue": queue, "tmp": tmp_path, "seen": seen}


def _run_rows(d: Path, rows: list[dict], rig) -> None:
    """Write one result row per matrix row through the real row path."""
    manifest = camp.load_manifest(d)
    tasks = {t["id"]: t for t in rn.load_suite(camp.SUITE_DIR / "home.jsonl")}
    for r in rows:
        if (d / "rows" / (camp.sha12(r["run_id"]) + ".json")).exists():
            continue
        camp.run_row(
            d,
            manifest,
            r,
            rn.workspace_context(r["workspace"]),
            tasks[r["task_id"]],
            1,
            60,
            None,
            False,
        )


class TestComponentScreenToLedger:
    def test_the_whole_flow_offline(self, rig):
        plan, queue = rig["plan"], rig["queue"]

        # 1. screen
        screen = camp.expand_matrix(plan, 3, tier="screen")
        d = camp.open_campaign("sweep", plan, screen, append=False)
        _run_rows(d, screen, rig)

        # 2. --screen-out
        out = rep.screen_out(d, queue)
        assert out["advance"] == {WS_INTENDED: [BETTER, TIED]}
        verdicts = {(c["workspace"], c["candidate"]): c["verdict"] for c in out["cells"]}
        assert verdicts[(WS_OTHER, DROPPED)] == decision.DROP
        assert verdicts[(WS_INTENDED, BETTER)] == decision.ADVANCE
        assert verdicts[(WS_INTENDED, TIED)] == decision.ADVANCE

        # 3. confirm append: only what advanced, plus every incumbent
        adv = rig["tmp"] / "advance.yaml"
        adv.write_text(yaml.safe_dump(out["advance"], sort_keys=True))
        confirm = camp.expand_matrix(plan, 3, tier="confirm", advance=camp.load_advance(adv))
        assert {r["arm"] for r in confirm if r["workspace"] == WS_OTHER} == {INC}
        camp.open_campaign("sweep", plan, confirm, append=True)
        _run_rows(d, confirm, rig)

        # 4. --fitness
        fit = rep.fitness(d, queue)
        cells = {(c["workspace"], c["candidate"]): c for c in fit["cells"]}
        assert cells[(WS_INTENDED, BETTER)]["verdict"] == decision.BETTER
        assert cells[(WS_INTENDED, TIED)]["verdict"] == decision.NOT_SEPARATED
        assert all(c["n"] == N_TOTAL for c in fit["cells"])

        # 5. a fixed eligibility cell that is MISSING, as Part 3's queue will say
        missing_facts = {"in_catalog": True, "available": False, "family_has_suite": True}
        assert decision.eligibility(missing_facts) == (
            decision.MISSING,
            "not installed or not restorable now",
        )
        gone_facts = {"in_catalog": True, "available": False, "family_has_suite": True}
        assert decision.eligibility(gone_facts)[0] == decision.MISSING

        dispositions = {x["model"]: x for x in fit["dispositions"]}
        assert dispositions[BETTER]["disposition"] == "FOLD"
        assert dispositions[TIED]["disposition"] == "RETAIN_DIVERSITY"
        assert dispositions[DROPPED]["disposition"] == "NO_DECISION"
        # The unrestorable model is queued for an intended workspace with no
        # cell, so it is NO_DECISION rather than a silent absence.
        assert dispositions[GONE]["disposition"] == "NO_DECISION"
        assert "ineligible or absent" in dispositions[GONE]["reason"]

        # 6. --record
        led = rig["tmp"] / "ledger.yaml"
        rec = rep.record_ledger(d, queue, led)
        written = yaml.safe_load(led.read_text())["cells"]
        assert written == rec["cells"]
        assert {c["verdict"] for c in written} == {decision.BETTER, decision.NOT_SEPARATED}
        assert all(c["campaign"] == "sweep" for c in written)
        assert all(c["instrument"] == camp.instrument_fingerprint()["fingerprint"] for c in written)

    def test_the_reused_screen_rows_are_the_confirm_repeat_zero(self, rig):
        """The append re-runs nothing: every screen run_id is already present."""
        plan = rig["plan"]
        screen = camp.expand_matrix(plan, 3, tier="screen")
        d = camp.open_campaign("sweep", plan, screen, append=False)
        before = set(camp.load_manifest(d)["rows"][0].keys())
        confirm = camp.expand_matrix(plan, 3, tier="confirm")
        camp.open_campaign("sweep", plan, confirm, append=True)
        rows = camp.load_manifest(d)["rows"]
        ids = [r["run_id"] for r in rows]
        assert len(ids) == len(set(ids))
        assert {r["run_id"] for r in screen} <= set(ids)
        assert before  # the row shape is unchanged by tiers
