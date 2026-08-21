"""TASK_BULLY_INVESTIGATION_V1 (I.4): cousins injected inside the corpus
time range.

`plan_cousins` and `cousin_inject.inject_cousins` must place every injected
event inside the corpus's own real time range (I5), never at "now" -- the
T.3 defect (cousins shipped ~8 years outside every BOTS index).
"""

from __future__ import annotations

import dataclasses

import pytest

from portal.modules.security.core.bully import corpus_bed, cousin_inject
from portal.modules.security.core.bully.bots_answer_key import BOTS_ANSWER_KEY

# botsv3's real, live-discovered single-day scenario window.
BOTSV3_EARLIEST = 1534737600.0
BOTSV3_LATEST = 1534824000.0

# The T.3 configuration: cousins shipped at "now" (2026), ~8 years outside
# every BOTS index. Permanent regression case.
T3_NOW_2026 = 1787316013.0


def test_every_planned_cousin_lands_inside_the_corpus_range():
    cousins = corpus_bed.plan_cousins(
        list(BOTS_ANSWER_KEY),
        corpus_earliest=BOTSV3_EARLIEST,
        corpus_latest=BOTSV3_LATEST,
    )
    assert cousins
    for cousin in cousins:
        assert BOTSV3_EARLIEST <= cousin.injected_at <= BOTSV3_LATEST


def test_cousin_carries_anchor_entity_when_answer_key_has_one():
    entry = corpus_bed.AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",
        behavioural_spine=("a", "b"),
        entities=("web_admin",),
        sourcetypes=("aws:cloudtrail",),
    )
    cousins = corpus_bed.plan_cousins(
        [entry], corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
    )
    assert all(c.anchor_entity == "web_admin" for c in cousins)


def test_cousin_lands_adjacent_to_parents_confirmed_activity():
    entry = corpus_bed.AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",
        behavioural_spine=("a", "b"),
        sourcetypes=("aws:cloudtrail",),
        confirmed_at=BOTSV3_EARLIEST + 9 * 3600,
    )
    cousins = corpus_bed.plan_cousins(
        [entry], corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
    )
    for c in cousins:
        assert abs(c.injected_at - entry.confirmed_at) < 3600 * 2


def test_a_cousin_planned_with_a_now_timestamp_is_refused():
    """Seeded violation: a hand-constructed cousin carrying the exact T.3
    configuration (a 2026 'now' timestamp) must be refused, not shipped."""
    cousins = corpus_bed.plan_cousins(
        [BOTS_ANSWER_KEY[0]], corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
    )
    bad_cousin = dataclasses.replace(cousins[0], injected_at=T3_NOW_2026)
    with pytest.raises(
        corpus_bed.CousinOutsideCorpusRangeError, match="cousin_outside_corpus_range"
    ):
        corpus_bed.validate_cousin_in_range(
            bad_cousin, corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
        )


def test_t3_configuration_refused_outright_by_inject_cousins(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cousin_inject, "ship_batch", lambda events, **kw: calls.append(kw) or {"ok": True}
    )
    cousins = corpus_bed.plan_cousins(
        [BOTS_ANSWER_KEY[0]], corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
    )
    bad_cousin = dataclasses.replace(cousins[0], injected_at=T3_NOW_2026)
    with pytest.raises(corpus_bed.CousinOutsideCorpusRangeError):
        cousin_inject.inject_cousins(
            [bad_cousin],
            dry_run=True,
            corpus_earliest=BOTSV3_EARLIEST,
            corpus_latest=BOTSV3_LATEST,
        )
    assert not calls  # nothing was shipped


def test_injected_cousin_is_reachable_from_a_corpus_clamped_investigation():
    from portal.modules.security.core.bully import investigation_pivot as ip

    entry = corpus_bed.AnswerKeyEntry(
        dataset="botsv3",
        technique="T1558.004",
        behavioural_spine=("a", "b"),
        entities=("BSTOLL-L",),
        sourcetypes=("aws:cloudtrail",),
        confirmed_at=BOTSV3_EARLIEST + 9 * 3600,
    )
    cousins = corpus_bed.plan_cousins(
        [entry], corpus_earliest=BOTSV3_EARLIEST, corpus_latest=BOTSV3_LATEST
    )
    cousin = cousins[0]

    events = [
        {
            "_time": cousin.injected_at,
            "index": "botsv3",
            "sourcetype": "corpus:cousin",
            "entity": cousin.anchor_entity,
        }
    ]

    def execute(query):
        return [
            e
            for e in events
            if e["entity"] == query.entity and query.earliest <= e["_time"] <= query.latest
        ]

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=entry.confirmed_at,
        entity="BSTOLL-L",
        entity_kind="host",
        sourcetype="aws:cloudtrail",
        why="test",
        index="botsv3",
    )
    inv = ip.investigate(
        anchor,
        ["botsv3"],
        execute,
        lambda row: [],
        corpus_earliest=BOTSV3_EARLIEST,
        corpus_latest=BOTSV3_LATEST,
    )
    assert any(e["sourcetype"] == "corpus:cousin" for e in inv.events)
