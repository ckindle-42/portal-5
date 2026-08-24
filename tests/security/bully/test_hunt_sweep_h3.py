"""H.3 -- hunt-loop checkpoint and incremental publication
(TASK_BULLY_HUNT_SWEEP_V1). Seeded to fail against a naive/no-op
implementation: killing the run mid-sweep and resuming continues at the
next unattempted entry with prior results intact; the partial doc is
readable at any point."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry  # noqa: E402
from portal.modules.security.core.bully.full_pipeline import RunContext  # noqa: E402


def _entry(technique: str) -> AnswerKeyEntry:
    return AnswerKeyEntry(
        dataset="botsv3",
        technique=technique,
        behavioural_spine=("auth", "escalate"),
        entities=(f"host-{technique}",),
        sourcetypes=("wineventlog:security",),
    )


class _FakeRange:
    earliest = 1000.0
    latest = 50_000.0


def _ctx() -> RunContext:
    ctx = RunContext()
    ctx.put("indexes", ("botsv3",))
    ctx.put("index_ranges", {"botsv3": _FakeRange()})
    ctx.put("corpus_earliest", 0.0)
    ctx.put("corpus_latest", 100_000.0)
    return ctx


def _stage_for(name: str, **build_kwargs):
    stages = fa.build_stages(
        max_records=None,
        batch_size=10,
        per_sourcetype_cap=10,
        dry_run_cousins=True,
        **build_kwargs,
    )
    return next(s for s in stages if s.name == name)


def test_checkpoint_roundtrips_hunt_state(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    from portal.modules.security.core.bully import run_preflight as rpf

    progress = rpf.EntryProgress()
    progress.entries_done.append("T0001")
    progress.planted_cousins["T0001"] = "cz-T0001-000"
    progress.results.append({"technique": "T0001", "located": True})

    fa._save_hunt_checkpoint(progress, span_seconds=600.0)
    loaded = fa._load_hunt_checkpoint()
    assert loaded is not None
    loaded_progress, span = loaded
    assert loaded_progress.entries_done == ["T0001"]
    assert loaded_progress.planted_cousins == {"T0001": "cz-T0001-000"}
    assert span == 600.0


def test_hunt_checkpoint_coexists_with_stream_checkpoint(tmp_path, monkeypatch):
    """The hunt checkpoint is merged into the SAME file the stream stage
    uses -- writing one must never clobber the other's keys."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    from portal.modules.security.core.bully import run_preflight as rpf

    fa._save_checkpoint({"all_indexes": ["botsv3"], "covered": [["botsv3", "st1"]]})
    progress = rpf.EntryProgress()
    progress.entries_done.append("T0001")
    fa._save_hunt_checkpoint(progress, span_seconds=600.0)

    on_disk = json.loads(fa.CHECKPOINT_PATH.read_text())
    assert on_disk["all_indexes"] == ["botsv3"]
    assert on_disk["hunt_entries_done"] == ["T0001"]


@patch("bully_full_assembly_run.cousin_inject.inject_cousins")
@patch("bully_full_assembly_run._read_window_completely")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_killed_mid_sweep_resumes_at_next_unattempted_entry_with_prior_results_intact(
    mock_connector, mock_read, mock_inject, tmp_path, monkeypatch
):
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    mock_connector.return_value = object()
    mock_inject.return_value = []

    all_entries = tuple(_entry(f"T{i:04d}") for i in range(1, 5))  # T0001..T0004

    # Each located entry reads its window twice (locate, then post-plant
    # re-hunt): calls 1-2 finish entry 1, calls 3-4 finish entry 2, and the
    # 5th call -- entry 3's locate read -- is where the process "dies",
    # leaving entry 3 unrecorded and entry 4 never attempted.
    reads = {"n": 0}

    def fake_read(connector, index, start, end):
        reads["n"] += 1
        if reads["n"] == 5:
            raise RuntimeError("simulated kill mid-sweep")
        return [
            {"host": e.entities[0], "sourcetype": "wineventlog:security", "_time": 1.0}
            for e in all_entries
        ]

    mock_read.side_effect = fake_read

    with patch.object(fa, "BOTS_ANSWER_KEY", all_entries):
        stage = _stage_for("investigate_anchors")
        with pytest.raises(RuntimeError, match="simulated kill mid-sweep"):
            stage.run(_ctx())

        # checkpoint on disk after the "kill" must show exactly entries 1-2 done.
        loaded = fa._load_hunt_checkpoint()
        assert loaded is not None
        progress_after_kill, _span = loaded
        assert progress_after_kill.entries_done == ["botsv3:T0001", "botsv3:T0002"]

        # a fresh process (hunt_progress=None) resumes from disk and finishes
        # the remaining entries without re-attempting or re-planting 1-2.
        resumed_stage = _stage_for("investigate_anchors")
        result = resumed_stage.run(_ctx())

    assert result["n_entries_attempted"] == 4
    assert result["n_entries_not_attempted"] == 0
    final_progress = fa._load_hunt_checkpoint()[0]
    assert final_progress.entries_done == [
        "botsv3:T0001",
        "botsv3:T0002",
        "botsv3:T0003",
        "botsv3:T0004",
    ]
    # entries 1-2's own results must still be present, not overwritten by
    # the resumed run.
    techniques_in_results = [r["technique"] for r in final_progress.results]
    assert techniques_in_results == ["T0001", "T0002", "T0003", "T0004"]
    # inject_cousins called exactly once per (located) entry across BOTH the
    # crashed attempt and the resumed one -- never re-invoked for 1-2.
    assert mock_inject.call_count == 4


def test_on_entry_done_publishes_a_readable_partial_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    from portal.modules.security.core.bully import run_preflight as rpf

    partial_path = tmp_path / "RUN_PARTIAL.json"
    written: list[dict] = []

    def on_entry_done(progress: rpf.EntryProgress, result: dict) -> None:
        partial_path.write_text(
            json.dumps({"entry_progress": progress.to_dict(), "last_entry": result})
        )
        written.append(json.loads(partial_path.read_text()))

    all_entries = (_entry("T0001"),)

    def fake_read(connector, index, start, end):
        return [{"host": "host-T0001", "sourcetype": "wineventlog:security", "_time": 1.0}]

    with (
        patch.object(fa, "BOTS_ANSWER_KEY", all_entries),
        patch("bully_full_assembly_run._read_window_completely", side_effect=fake_read),
        patch("bully_full_assembly_run.cousin_inject.inject_cousins", return_value=[]),
        patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector"),
    ):
        stage = _stage_for("investigate_anchors", on_entry_done=on_entry_done)
        stage.run(_ctx())

    assert partial_path.exists()
    doc = json.loads(partial_path.read_text())
    assert doc["entry_progress"]["n_done"] == 1
    assert doc["last_entry"]["technique"] == "T0001"
    assert len(written) == 1  # published once, right after the one entry finished
