"""Offline tests for the campaign finish verdict — the receipt-facing exit.

Incident realuse_s8_20261030: 3 of 68 rows recorded, every arm STOPPED on
instrument drift, and the driver still exited 0 (receipt PASS). A campaign
that did not complete its matrix must not exit 0.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tests.wfe import campaign


def _campaign_dir(tmp_path: Path, rows: list[dict]) -> Path:
    d = tmp_path / "campaigns" / "s8"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return d


def _rows(*states: str) -> list[dict]:
    return [{"state": s} for s in states]


def _finish(monkeypatch, campaign_dir: Path) -> int:
    monkeypatch.setattr(campaign, "CAMPAIGNS", campaign_dir.parent)
    monkeypatch.setattr(sys, "argv", ["campaign", "--campaign-id", "s8", "--finish"])
    return campaign._cli()


def _last_line(capsys) -> str:
    return capsys.readouterr().out.strip().splitlines()[-1]


def test_a_stop_exits_five_and_names_itself_on_the_last_line(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    d = _campaign_dir(tmp_path, _rows(*(["PASS"] * 3 + ["PENDING"] * 65)))
    (d / "arm_stops.jsonl").write_text(
        json.dumps({"arm": "m1", "reason": "instrument drift in ['harness']: baseline a now b"})
        + "\n",
        encoding="utf-8",
    )

    assert _finish(monkeypatch, d) == campaign.EXIT_STOPPED == 5
    assert _last_line(capsys) == (
        "CAMPAIGN s8: stopped (instrument drift in ['harness']: baseline a now b) rows 3/68"
    )


def test_a_completed_matrix_exits_zero_and_says_complete(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    d = _campaign_dir(tmp_path, _rows("PASS", "FAIL", "SKIPPED_DECIDED"))

    assert _finish(monkeypatch, d) == 0
    assert _last_line(capsys) == "CAMPAIGN s8: complete (all rows measured) rows 3/3"


def test_a_halt_is_a_result_summarised_on_the_last_line(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    d = _campaign_dir(tmp_path, _rows(*(["PASS"] * 4 + ["PENDING"] * 2)))
    (d / "arm_exits.log").write_text("HALT m2 math 0 tool calls on all 4 rows\n", encoding="utf-8")

    assert _finish(monkeypatch, d) == 0
    assert _last_line(capsys) == (
        "CAMPAIGN s8: complete (1 halt(s): m2 math 0 tool calls on all 4 rows) rows 4/6"
    )


def test_nothing_measured_keeps_exit_ten_and_still_prints_the_final_line(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    d = _campaign_dir(tmp_path, _rows("PENDING", "BLOCKED", "MISSING"))

    assert _finish(monkeypatch, d) == campaign.EXIT_NOTHING_MEASURED == 10
    out = capsys.readouterr().out.strip().splitlines()
    assert out == [
        "OVERHEAD harness_s=0.000 model_s=0.000 ratio=0.000",
        "unattributed_s=0.000",
        "NOTHING MEASURED: 1 PENDING",
        "CAMPAIGN s8: stopped (nothing measured: 1 PENDING) rows 0/3",
    ]


def test_pending_rows_without_a_stop_record_are_incomplete(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    d = _campaign_dir(tmp_path, _rows("PASS", "PENDING"))

    assert _finish(monkeypatch, d) == campaign.EXIT_INCOMPLETE == 8
    assert _last_line(capsys) == (
        "CAMPAIGN s8: stopped (1 row(s) left PENDING with no stop recorded) rows 1/2"
    )


def test_blocked_rows_are_named_on_a_complete_run(tmp_path: Path, monkeypatch, capsys) -> None:
    d = _campaign_dir(tmp_path, _rows("PASS", "PASS", "BLOCKED"))

    assert _finish(monkeypatch, d) == 0
    assert _last_line(capsys) == "CAMPAIGN s8: complete (1 row(s) BLOCKED, rest measured) rows 2/3"


def test_a_stop_outranks_nothing_measured(tmp_path: Path, monkeypatch, capsys) -> None:
    d = _campaign_dir(tmp_path, _rows("BLOCKED", "PENDING", "MISSING"))
    (d / "arm_stops.jsonl").write_text(
        json.dumps({"arm": "m1", "reason": "seat block: pipeline served x"}) + "\n",
        encoding="utf-8",
    )

    assert _finish(monkeypatch, d) == 5
    assert _last_line(capsys) == "CAMPAIGN s8: stopped (seat block: pipeline served x) rows 0/3"


def test_missing_manifest_is_nothing_measured(tmp_path: Path, monkeypatch, capsys) -> None:
    d = tmp_path / "campaigns" / "s8"
    d.mkdir(parents=True)

    assert _finish(monkeypatch, d) == 10
    assert _last_line(capsys) == "CAMPAIGN s8: stopped (nothing measured: no rows) rows 0/0"


def test_an_arm_stop_is_recorded_for_the_finish_verdict(tmp_path: Path, monkeypatch) -> None:
    d = tmp_path / "c"
    d.mkdir()
    monkeypatch.setattr(campaign, "drain_model", lambda tag: True)

    campaign._finish_arm(
        d, "m1", "model-x", {"PASS": 1}, time.monotonic(), False, "drift: harness", None, 1
    )

    stops = [json.loads(ln) for ln in (d / "arm_stops.jsonl").read_text().splitlines()]
    assert stops == [{"arm": "m1", "reason": "drift: harness"}]


def test_record_arm_stop_appends_across_arms(tmp_path: Path) -> None:
    d = tmp_path / "c"
    d.mkdir()

    campaign.record_arm_stop(d, "m1", "first")
    campaign.record_arm_stop(d, "m2", "second")

    stops = campaign._recorded_stops(d)
    assert [s["arm"] for s in stops] == ["m1", "m2"]
    assert stops[-1]["reason"] == "second"


def test_time_cap_is_persisted_and_named_by_finish(tmp_path: Path, monkeypatch, capsys) -> None:
    d = _campaign_dir(tmp_path, _rows("PENDING", "PENDING"))
    manifest = {
        "rows": [
            {
                "arm": arm,
                "arm_role": role,
                "workspace": "ws",
                "suite": "s",
                "task_id": "t0",
                "repeat": 0,
                "run_id": arm,
                "state": "PENDING",
            }
            for arm, role in (("inc", "incumbent"), ("cand", "challenger"))
        ]
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(campaign.time, "time", lambda: 1000.0)

    outs = campaign._run_interleaved_campaign(
        d,
        ["inc", "cand"],
        type("Args", (), {"rerun_failed": False, "no_curtail": False, "budget_s": 1800})(),
        {"interleave_block": 1},
        deadline_epoch=999.0,
    )

    saved = json.loads((d / "manifest.json").read_text())
    assert outs == [{"stopped": "time cap"}]
    assert saved["campaign_stop"]["reason"] == "time cap"
    assert _finish(monkeypatch, d) == campaign.EXIT_STOPPED
    assert _last_line(capsys) == "CAMPAIGN s8: stopped (time cap) rows 0/2"


def test_interleaved_runner_reoffers_decided_rows_when_no_curtail_is_requested(
    tmp_path: Path, monkeypatch
) -> None:
    d = _campaign_dir(tmp_path, [])
    decision_id = "cand:ws"
    rows = [
        {
            "arm": arm,
            "arm_role": role,
            "workspace": "ws",
            "suite": "s",
            "task_id": "t0",
            "repeat": 0,
            "run_id": f"{arm}:t0",
            "tier": "confirm",
            "state": "SKIPPED_DECIDED",
            **({"curtailment_id": decision_id} if arm == "cand" else {}),
        }
        for arm, role in (("inc", "incumbent"), ("cand", "challenger"))
    ]
    manifest = {
        "rows": rows,
        "curtailments": [{"id": decision_id, "arm": "cand", "state": "CURTAILED"}],
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    observed = []

    def run_block(campaign_dir, block, _arms, _args, _budget):
        ids = {
            run_id for unit in block for run_ids in unit["run_ids"].values() for run_id in run_ids
        }
        observed.extend(sorted(ids))
        current = campaign.load_manifest(campaign_dir)
        for row in current["rows"]:
            if row["run_id"] in ids:
                row["state"] = "PASS"
        campaign.save_manifest(campaign_dir, current)
        return [{"ran": len(ids)}]

    monkeypatch.setattr(campaign, "_run_interleaved_block", run_block)
    args = type("Args", (), {"no_curtail": True, "rerun_failed": False, "budget_s": 1800})()

    campaign._run_interleaved_campaign(
        d,
        ["inc", "cand"],
        args,
        {"interleave_block": 1, "pilot_tasks": None},
        deadline_epoch=time.time() + 60,
    )

    saved = campaign.load_manifest(d)
    assert observed == ["cand:t0", "inc:t0"] or observed == ["inc:t0", "cand:t0"]
    assert all(row["state"] == "PASS" for row in saved["rows"])
    assert saved["curtailments"] == []
    assert saved["curtailment_history"][0]["state"] == "RESUMED_NO_CURTAIL"


def test_interleaved_runner_stops_after_a_persistent_preflight_block(
    tmp_path: Path, monkeypatch
) -> None:
    d = _campaign_dir(tmp_path, [])
    rows = [
        {
            "arm": arm,
            "arm_role": role,
            "workspace": "ws",
            "suite": "s",
            "task_id": "t0",
            "repeat": 0,
            "run_id": f"{arm}:t0",
            "tier": "confirm",
            "state": "PENDING",
        }
        for arm, role in (("inc", "incumbent"), ("cand", "challenger"))
    ]
    (d / "manifest.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    calls = 0

    def blocked_block(campaign_dir, block, _arms, _args, _budget):
        nonlocal calls
        calls += 1
        assert calls == 1, "persistent preflight blocks must not be retried in a busy loop"
        manifest = campaign.load_manifest(campaign_dir)
        for row in manifest["rows"]:
            row.update(state="BLOCKED", note=campaign._PREFLIGHT_BLOCK + "stale readiness")
        campaign.save_manifest(campaign_dir, manifest)
        return [{"blocked": True}]

    monkeypatch.setattr(campaign, "_run_interleaved_block", blocked_block)
    args = type("Args", (), {"no_curtail": False, "rerun_failed": False, "budget_s": 1800})()

    outs = campaign._run_interleaved_campaign(
        d,
        ["inc", "cand"],
        args,
        {"interleave_block": 1, "pilot_tasks": None},
        deadline_epoch=time.time() + 60,
    )

    assert calls == 1
    assert outs == [{"blocked": True}]


def test_interleaved_decision_curtails_both_arms_and_stops_campaign(
    tmp_path: Path, monkeypatch
) -> None:
    d = _campaign_dir(tmp_path, [])
    rows = []
    for i in range(40):
        for arm, role, outcome in (
            ("inc", "incumbent", "FAIL"),
            ("cand", "challenger", "PASS"),
        ):
            rows.append(
                {
                    "arm": arm,
                    "arm_role": role,
                    "workspace": "ws",
                    "suite": "s",
                    "suite_path": "s.jsonl",
                    "task_id": f"t{i}",
                    "repeat": 0,
                    "run_id": f"{arm}:t{i}",
                    "tier": "confirm",
                    "state": outcome if i < 30 else "PENDING",
                }
            )
    manifest = {"campaign_id": "s8", "rows": rows, "execution": {}}
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(campaign, "load_suite", lambda _path: [])
    monkeypatch.setattr(
        campaign,
        "_manifest_row_result",
        lambda _directory, row: {**row, "outcome": row["state"]},
    )

    _new, stopped = campaign._evaluate_interleaved(d, manifest, ["inc", "cand"], 0.0)

    saved = json.loads((d / "manifest.json").read_text())
    assert stopped is True
    assert saved["campaign_stop"]["kind"] == "decision"
    (record,) = [r for r in saved["curtailments"] if r["arm"] == "cand"]
    assert record["verdict"] == "BETTER"
    assert not any(r["state"] == "PENDING" for r in saved["rows"])
