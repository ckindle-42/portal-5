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
