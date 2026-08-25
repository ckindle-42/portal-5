"""H.2 -- widen the locate-plant-hunt loop to the whole answer key, keep it
intact (TASK_BULLY_HUNT_SWEEP_V1). Seeded to fail against a naive/no-op
implementation: a run resumed after entry 5 does not re-plant entries 1-5;
an entry whose window is sampled raises rather than proceeding."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully import run_preflight as rpf  # noqa: E402
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


def _fake_window_read(entity: str, n: int = 3) -> list[dict]:
    return [{"host": entity, "sourcetype": "wineventlog:security", "_time": 1.0}] * n


def _ctx_for(entries: tuple[AnswerKeyEntry, ...]) -> RunContext:
    ctx = RunContext()
    ctx.put("indexes", ("botsv3",))
    ctx.put("index_ranges", {"botsv3": _FakeRange()})
    ctx.put("corpus_earliest", 0.0)
    ctx.put("corpus_latest", 100_000.0)
    return ctx


class _FakeRange:
    earliest = 1000.0
    latest = 50_000.0


def _stage_for(name: str, **build_kwargs):
    stages = fa.build_stages(
        max_records=None,
        batch_size=10,
        per_sourcetype_cap=10,
        dry_run_cousins=True,
        **build_kwargs,
    )
    return next(s for s in stages if s.name == name)


@patch("bully_full_assembly_run.cousin_inject.inject_cousins")
@patch("bully_full_assembly_run._read_window_completely")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_resumed_run_never_replants_entries_1_through_5(
    mock_connector, mock_read, mock_inject, tmp_path, monkeypatch
):
    # `investigate_anchors` checkpoints after every entry regardless of
    # whether `hunt_progress` was passed explicitly -- isolate from the
    # real CHECKPOINT_PATH or this test pollutes /tmp for any real run.
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    mock_connector.return_value = object()
    mock_inject.return_value = []

    all_entries = tuple(_entry(f"T{i:04d}") for i in range(1, 8))
    with patch.object(fa, "BOTS_ANSWER_KEY", all_entries):
        # Pre-loaded progress: entries 1-5 already done, technique 1-5 already
        # planted (simulating a prior attempt that shipped their cousins).
        progress = rpf.EntryProgress()
        for i in range(1, 6):
            technique = f"T{i:04d}"
            entities = (f"host-{technique}",)
            progress.entries_done.append(rpf.entry_key("botsv3", technique, entities))
            progress.record_plant("botsv3", technique, f"cz-{technique}-000", entities=entities)
            progress.results.append(
                {
                    "technique": technique,
                    "located": True,
                    "cousin_planted": True,
                    "cousin_recovered": True,
                }
            )

        def fake_read(connector, index, start, end):
            # every window "contains" every entry's own entity -- located
            # is always true so the resumed entries (6, 7) would plant if
            # not already-planted-guarded.
            return _fake_window_read("any", n=1) + [
                {"host": e.entities[0], "sourcetype": "wineventlog:security", "_time": 1.0}
                for e in all_entries
            ]

        mock_read.side_effect = fake_read

        stage = _stage_for("investigate_anchors", hunt_progress=progress)
        ctx = _ctx_for(all_entries)
        stage.run(ctx)

    # inject_cousins must only be called for entries 6 and 7 (not already
    # planted) -- never re-invoked for 1-5.
    planted_techniques_this_run = [call.kwargs.get("index") for call in mock_inject.call_args_list]
    assert mock_inject.call_count == 2, (
        f"expected exactly 2 new plants (entries 6,7), got {mock_inject.call_count} "
        f"calls: {planted_techniques_this_run}"
    )
    for i in range(1, 6):
        technique = f"T{i:04d}"
        entities = (f"host-{technique}",)
        assert progress.already_planted("botsv3", technique, entities) == f"cz-{technique}-000"


@patch("bully_full_assembly_run._window_count")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_sampled_window_raises_rather_than_proceeding(mock_connector, mock_window_count):
    """A window read that returns fewer rows than the window's true count is
    a sampled window, not a complete one -- H2 requires this to raise."""

    class _Result:
        records = [{"host": "h1", "sourcetype": "wineventlog:security", "_time": 1.0}]

    def fake_read(_intent):
        return _Result()

    connector = type("FakeConnector", (), {"read": staticmethod(fake_read)})()
    mock_window_count.return_value = 500  # true count vastly exceeds what "read" returns

    with pytest.raises(fa.SampledWindowError):
        fa._read_window_completely(connector, "botsv3", 0.0, 600.0)


@patch("bully_full_assembly_run.time.sleep")
@patch("bully_full_assembly_run._read_window_completely")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_one_entrys_sampled_window_does_not_abort_the_remaining_sweep(
    mock_connector, mock_read, _mock_sleep, tmp_path, monkeypatch
):
    """A SampledWindowError on entry 2 (a live-indexing-lag race, not a
    process crash) must be recorded against that one entry and the sweep
    must continue to entries 3+ -- not lose the rest of the answer key to
    one flaky window, and not silently drop them from
    `entries_not_attempted` either."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    mock_connector.return_value = object()

    all_entries = tuple(_entry(f"T{i:04d}") for i in range(1, 4))  # T0001..T0003

    def fake_read(connector, index, start, end):
        return [
            {"host": e.entities[0], "sourcetype": "wineventlog:security", "_time": 1.0}
            for e in all_entries
        ]

    call_count = {"n": 0}

    def fake_read_with_failure(connector, index, start, end):
        call_count["n"] += 1
        # Entry 1 locates cleanly (its own locate + post-plant recovery
        # reads are calls 1-2). Entry 2's locate read then fails on BOTH
        # its first attempt and its retry (calls 3-4) -- a persistent, not
        # transient, incomplete window, so it never reaches a recovery
        # read at all. Entry 3 (calls 5-6) locates cleanly again.
        if call_count["n"] in (3, 4):
            raise fa.SampledWindowError("botsv3 window sampled, not complete")
        return fake_read(connector, index, start, end)

    mock_read.side_effect = fake_read_with_failure

    with patch.object(fa, "BOTS_ANSWER_KEY", all_entries):
        stage = _stage_for("investigate_anchors")
        ctx = _ctx_for(all_entries)
        result = stage.run(ctx)

    assert result["n_entries_attempted"] == 3
    assert result["n_entries_not_attempted"] == 0
    progress = ctx.get("entry_progress")
    by_technique = {r["technique"]: r for r in progress.results}
    assert by_technique["T0001"]["located"] is True
    assert by_technique["T0002"]["located"] is False
    assert "SampledWindowError" in by_technique["T0002"]["error"]
    assert by_technique["T0003"]["located"] is True


@patch("bully_full_assembly_run.cousin_inject.inject_cousins")
@patch("bully_full_assembly_run._read_window_completely")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_same_technique_across_two_datasets_are_both_attempted(
    mock_connector, mock_read, mock_inject, tmp_path, monkeypatch
):
    """The real BOTS answer key has genuine technique-ID collisions across
    datasets (T1071.001 in botsv3, botsv2, and twice in botsv1 alone). A
    sweep over an entry list with the same technique in two different
    datasets must attempt BOTH -- not silently treat the second as
    already-done because it shares a bare technique id with the first
    (the exact defect that dropped 7-8 real entries from a live 27/28-entry
    sweep: they never appeared in entries_done OR entries_not_attempted,
    they simply vanished)."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    mock_connector.return_value = object()
    mock_inject.return_value = []

    def _entry_ds(dataset: str, technique: str) -> AnswerKeyEntry:
        return AnswerKeyEntry(
            dataset=dataset,
            technique=technique,
            behavioural_spine=("auth", "escalate"),
            entities=(f"host-{dataset}-{technique}",),
            sourcetypes=("wineventlog:security",),
        )

    all_entries = (
        _entry_ds("botsv3", "T1071.001"),
        _entry_ds("botsv2", "T1071.001"),
        _entry_ds("botsv1", "T1071.001"),
    )

    def fake_read(connector, index, start, end):
        return [
            {"host": e.entities[0], "sourcetype": "wineventlog:security", "_time": 1.0}
            for e in all_entries
        ]

    mock_read.side_effect = fake_read

    ctx = RunContext()
    ctx.put("indexes", ("botsv3", "botsv2", "botsv1"))
    ctx.put(
        "index_ranges",
        {ds: _FakeRange() for ds in ("botsv3", "botsv2", "botsv1")},
    )
    ctx.put("corpus_earliest", 0.0)
    ctx.put("corpus_latest", 100_000.0)

    with patch.object(fa, "BOTS_ANSWER_KEY", all_entries):
        stage = _stage_for("investigate_anchors")
        result = stage.run(ctx)

    assert result["n_entries_attempted"] == 3
    assert result["n_entries_not_attempted"] == 0
    progress = ctx.get("entry_progress")
    datasets_seen = sorted(r["dataset"] for r in progress.results)
    assert datasets_seen == ["botsv1", "botsv2", "botsv3"]
    assert mock_inject.call_count == 3, (
        f"expected a separate plant for each dataset's own T1071.001, got {mock_inject.call_count}"
    )


@patch("bully_full_assembly_run.cousin_inject.inject_cousins")
@patch("bully_full_assembly_run._read_window_completely")
@patch("portal.modules.security.core.bully.live_connect.lab_splunk_connector")
def test_two_entries_sharing_dataset_and_technique_are_both_attempted(
    mock_connector, mock_read, mock_inject, tmp_path, monkeypatch
):
    """(dataset, technique) alone is STILL not a unique answer-key identity:
    the real answer key has two DIFFERENT confirmed botsv1/T1071.001
    entries (192.168.250.40 and .70, two source hosts against the same C2
    domain) -- live-verified, a run keyed on (dataset, technique) alone
    silently dropped the second one (26 done, 0 not-attempted, but the
    real answer key has 27 entries)."""
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    mock_connector.return_value = object()
    mock_inject.return_value = []

    all_entries = (
        AnswerKeyEntry(
            dataset="botsv1",
            technique="T1071.001",
            behavioural_spine=("c2_exfil",),
            entities=("192.168.250.40", "imreallynotbatman.com"),
            sourcetypes=("stream:http",),
        ),
        AnswerKeyEntry(
            dataset="botsv1",
            technique="T1071.001",
            behavioural_spine=("c2_exfil",),
            entities=("192.168.250.70", "imreallynotbatman.com"),
            sourcetypes=("stream:http",),
        ),
    )

    def fake_read(connector, index, start, end):
        return [
            {"host": e.entities[0], "sourcetype": "stream:http", "_time": 1.0} for e in all_entries
        ]

    mock_read.side_effect = fake_read

    ctx = RunContext()
    ctx.put("indexes", ("botsv1",))
    ctx.put("index_ranges", {"botsv1": _FakeRange()})
    ctx.put("corpus_earliest", 0.0)
    ctx.put("corpus_latest", 100_000.0)

    with patch.object(fa, "BOTS_ANSWER_KEY", all_entries):
        stage = _stage_for("investigate_anchors")
        result = stage.run(ctx)

    assert result["n_entries_attempted"] == 2
    assert result["n_entries_not_attempted"] == 0
    progress = ctx.get("entry_progress")
    assert len(progress.results) == 2
    assert mock_inject.call_count == 2, (
        f"expected a separate plant for each of the two distinct entries "
        f"sharing (dataset, technique), got {mock_inject.call_count}"
    )


def test_complete_window_read_with_matching_count_does_not_raise():
    class _Result:
        records = [{"host": "h1", "sourcetype": "wineventlog:security", "_time": 1.0}] * 3

    connector = type("FakeConnector", (), {"read": staticmethod(lambda _intent: _Result())})()
    with patch("bully_full_assembly_run._window_count", return_value=3):
        rows = fa._read_window_completely(connector, "botsv3", 0.0, 600.0)
    assert len(rows) == 3
