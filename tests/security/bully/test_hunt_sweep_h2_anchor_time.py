"""H.2 live-calibration finding: `_anchor_for`'s pre-existing fallback to
`rng.earliest` (the whole index's earliest record) meant every answer-key
entry without a hand-curated `confirmed_at` -- which is all 27 -- landed its
hunt window at the SAME instant regardless of technique, independent of
when that technique's own activity occurred. Live-verified against the real
lab Splunk: T1558.004's actual activity window (resolved via a term search)
found 36,640 records / 537 units in 10 minutes; the index-earliest window
found 9 records / 14 units 10 minutes after the index's first record --
almost certainly quiet time, not the documented technique.

`_resolve_anchor_time` fixes this: one cheap term search for the entity
across the full corpus range, taking the first hit's real `_time`, falling
back to `rng.earliest` only when the entity is not found at all."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bully_full_assembly_run as fa  # noqa: E402

from portal.modules.security.core.bully.corpus_bed import AnswerKeyEntry  # noqa: E402
from portal.modules.security.core.bully.full_pipeline import RunContext  # noqa: E402


class _FakeRange:
    earliest = 1_000_000.0
    latest = 2_000_000.0


def _entry() -> AnswerKeyEntry:
    return AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",
        behavioural_spine=("auth", "escalate"),
        entities=("BSTOLL-L",),
        sourcetypes=("wineventlog:security",),
    )


def _stage_for(name: str, **build_kwargs):
    stages = fa.build_stages(
        max_records=None,
        batch_size=10,
        per_sourcetype_cap=10,
        dry_run_cousins=True,
        **build_kwargs,
    )
    return next(s for s in stages if s.name == name)


def test_anchor_time_falls_back_to_index_earliest_when_entity_never_seen(tmp_path, monkeypatch):
    # `investigate_anchors` checkpoints after every entry regardless of
    # whether `hunt_progress` was passed explicitly -- isolate from the
    # real CHECKPOINT_PATH or this test pollutes /tmp for any real run.
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    entry = _entry()

    class _EmptyResult:
        records: list = []

    connector = type("FakeConnector", (), {"read": staticmethod(lambda intent: _EmptyResult())})()

    seen_windows = []

    def spy_read(conn, index, start, end):
        seen_windows.append((start, end))
        return []

    with (
        patch("bully_full_assembly_run._read_window_completely", side_effect=spy_read),
        patch(
            "portal.modules.security.core.bully.live_connect.lab_splunk_connector",
            return_value=connector,
        ),
        patch.object(fa, "BOTS_ANSWER_KEY", (entry,)),
    ):
        stage = _stage_for("investigate_anchors")
        ctx = RunContext()
        ctx.put("indexes", ("botsv3",))
        ctx.put("index_ranges", {"botsv3": _FakeRange()})
        ctx.put("corpus_earliest", 0.0)
        ctx.put("corpus_latest", 3_000_000.0)
        stage.run(ctx)

    assert len(seen_windows) == 1
    start, end = seen_windows[0]
    # window should be centered on rng.earliest (1_000_000.0) since the
    # entity resolution found nothing -- span 600s means start=999_700.
    assert 999_600.0 <= start <= 999_800.0


def test_anchor_time_centers_window_on_resolved_entity_time_not_index_earliest(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fa, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    entry = _entry()

    class _HitResult:
        records = [{"_time": 1_500_000.0, "host": "BSTOLL-L"}]

    connector = type("FakeConnector", (), {"read": staticmethod(lambda intent: _HitResult())})()

    seen_windows = []

    def spy_read(conn, index, start, end):
        seen_windows.append((start, end))
        return []

    with (
        patch("bully_full_assembly_run._read_window_completely", side_effect=spy_read),
        patch(
            "portal.modules.security.core.bully.live_connect.lab_splunk_connector",
            return_value=connector,
        ),
        patch.object(fa, "BOTS_ANSWER_KEY", (entry,)),
    ):
        stage = _stage_for("investigate_anchors")
        ctx = RunContext()
        ctx.put("indexes", ("botsv3",))
        ctx.put("index_ranges", {"botsv3": _FakeRange()})
        ctx.put("corpus_earliest", 0.0)
        ctx.put("corpus_latest", 3_000_000.0)
        stage.run(ctx)

    assert len(seen_windows) == 1
    start, end = seen_windows[0]
    # centered on the RESOLVED entity time (1_500_000.0), not rng.earliest
    # (1_000_000.0) -- this is the exact defect the live run surfaced.
    assert 1_499_600.0 <= start <= 1_499_800.0
