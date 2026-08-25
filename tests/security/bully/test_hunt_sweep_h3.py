"""H.3 -- hunt-loop checkpoint and incremental publication
(TASK_BULLY_HUNT_SWEEP_V1). Seeded to fail against a naive/no-op
implementation: killing the run mid-sweep and resuming continues at the
next unattempted entry with prior results intact; the partial doc is
readable at any point; a LATER stage's own checkpoint write must never
clobber the hunt loop's, whether mid-run or on that stage's own clean
finish (H5 follow-up: a rerun after this bug re-shipped 8 already-planted
cousins a second time into the real corpus, because the record of them
having been planted had been silently erased)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully import live_connect  # noqa: E402
from portal.modules.security.core.bully.connectors import (  # noqa: E402
    QUERY_IN_PLACE_MODE,
    NativeQuery,
    QueryResult,
)
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


def _fake_list_sourcetypes(_connector, _index):
    return [("sourcetype-0", 3)]


class _FakeStreamConnector:
    source_id = "lab-splunk-fake"
    mode = QUERY_IN_PLACE_MODE

    def translate(self, intent):
        return NativeQuery(self.source_id, "SPL", {"search": intent.seed.get("spl", "")}, intent)

    def read(self, intent):
        spl = intent.seed.get("spl", "")
        m = re.search(r'sourcetype="([^"]+)"', spl)
        st = m.group(1) if m else "unknown"
        records = tuple(
            {
                "_time": 1_700_000_000.0 + i,
                "host": f"host-{i}",
                "fields": {"sourcetype": st, "i": i},
            }
            for i in range(3)
        )
        return QueryResult(self.source_id, self.mode, self.translate(intent), records, 0.0, 0.0)


def _fake_lab_splunk_connector(*, source_id="lab-splunk", index=None):
    return _FakeStreamConnector()


def test_stream_stages_own_checkpoint_write_never_clobbers_hunt_state(tmp_path, monkeypatch):
    """`investigate_anchors` writes `hunt_*` keys into CHECKPOINT_PATH, then
    `stream_corpus_sample` (later in STAGE_PLAN, same run) checkpoints its
    OWN progress into the SAME file -- that write must merge, not replace,
    or it silently erases the hunt loop's state before the run even ends."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(fa, "_list_sourcetypes", _fake_list_sourcetypes)
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_lab_splunk_connector)

    from portal.modules.security.core.bully import run_preflight as rpf

    progress = rpf.EntryProgress()
    progress.record("botsv3", "T1558.004", {"located": True})
    progress.record_plant("botsv3", "T1558.004", "cz-botsv3-T1558.004-000")
    fa._save_hunt_checkpoint(progress, span_seconds=600.0)

    stages = fa.build_stages(
        max_records=None, batch_size=10_000, per_sourcetype_cap=2000, dry_run_cousins=True
    )
    stage = next(s for s in stages if s.name == "stream_corpus_sample")
    ctx = RunContext()
    ctx.put("indexes", ("test_index",))
    stage.run(ctx)

    on_disk = json.loads(fa.CHECKPOINT_PATH.read_text())
    assert on_disk.get("hunt_entries_done") == ["botsv3:T1558.004"], (
        f"stream_corpus_sample's own checkpoint write erased hunt_* state: {on_disk}"
    )
    assert on_disk.get("hunt_planted_cousins") == {"botsv3:T1558.004": "cz-botsv3-T1558.004-000"}


def test_stream_stages_clean_finish_does_not_delete_hunt_state(tmp_path, monkeypatch):
    """A run that finishes ALL sourcetypes deletes the stream stage's own
    checkpoint keys (by design -- a finished stream never resumes). It must
    NOT delete `hunt_*` keys: those are the only durable record of which
    cousins were shipped into the shared corpus, needed even after a
    successful run for the documented rollback path."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(fa, "_list_sourcetypes", _fake_list_sourcetypes)
    monkeypatch.setattr(live_connect, "lab_splunk_connector", _fake_lab_splunk_connector)

    from portal.modules.security.core.bully import run_preflight as rpf

    progress = rpf.EntryProgress()
    progress.record("botsv3", "T1558.004", {"located": True})
    progress.record_plant("botsv3", "T1558.004", "cz-botsv3-T1558.004-000")
    fa._save_hunt_checkpoint(progress, span_seconds=600.0)

    stages = fa.build_stages(
        max_records=None, batch_size=10_000, per_sourcetype_cap=2000, dry_run_cousins=True
    )
    stage = next(s for s in stages if s.name == "stream_corpus_sample")
    ctx = RunContext()
    ctx.put("indexes", ("test_index",))
    stage.run(ctx)  # covers the one sourcetype fully -> finished_all -> cleanup fires

    assert fa.CHECKPOINT_PATH.exists(), "hunt_* state must survive a clean finish, not vanish"
    on_disk = json.loads(fa.CHECKPOINT_PATH.read_text())
    assert on_disk.get("hunt_entries_done") == ["botsv3:T1558.004"]
    assert "all_indexes" not in on_disk  # the stream's own keys ARE cleared
    assert "covered" not in on_disk

    # a subsequent resume must recognise the already-planted cousin.
    loaded = fa._load_hunt_checkpoint()
    assert loaded is not None
    resumed_progress, _span = loaded
    assert resumed_progress.already_planted("botsv3", "T1558.004") == "cz-botsv3-T1558.004-000"
