"""TASK_BULLY_ADAPTIVE_REACH_V1 (A.4): cousins planted at a known pivot
DISTANCE, not always under the parent's own entity.

I.6 shipped every cousin under `anchor_entity == entities[0]` (0 hops): the
first entity-scoped query IS the query that finds it, so `20/20` recovery
measured planting position, not investigative reach. `plan_cousins` now
cycles cousins across every distance an `AnswerKeyEntry.entities_by_distance`
declares, and 0 hops is explicitly a CONTROL (`is_control: True`).
"""

from __future__ import annotations

from portal.modules.security.core.bully import adaptive_scope as ascope
from portal.modules.security.core.bully import corpus_bed

_CE, _CL = 1534737600.0, 1534824000.0


def _entry(**overrides):
    base = {
        "dataset": "botsv3",
        "technique": "T1558.004",
        "behavioural_spine": ("auth", "escalate"),
        "entities": ("BSTOLL-L",),
        "sourcetypes": ("wineventlog:security",),
        "confirmed_at": _CE + 9 * 3600,
    }
    base.update(overrides)
    return corpus_bed.AnswerKeyEntry(**base)


def test_with_no_distance_chain_every_cousin_is_the_0_hop_control():
    entry = _entry()  # entities_by_distance empty -- pre-A4 behaviour
    cousins = corpus_bed.plan_cousins([entry], corpus_earliest=_CE, corpus_latest=_CL)
    assert all(c.planted_distance == 0 for c in cousins)
    assert all(c.anchor_entity == "BSTOLL-L" for c in cousins)
    assert all(c.to_dict()["is_control"] for c in cousins)


def test_cousins_cycle_across_declared_distances():
    entry = _entry(
        entities_by_distance={
            0: "BSTOLL-L",
            1: "bstoll",
            2: "frothlywebcode",
            3: "web_admin",
        }
    )
    cousins = corpus_bed.plan_cousins(
        [entry],
        corpus_earliest=_CE,
        corpus_latest=_CL,
        transformations=corpus_bed.COUSIN_TRANSFORMATIONS,
    )
    distances_seen = {c.planted_distance for c in cousins}
    assert distances_seen == {0, 1, 2, 3}
    for c in cousins:
        expected_entity = {0: "BSTOLL-L", 1: "bstoll", 2: "frothlywebcode", 3: "web_admin"}[
            c.planted_distance
        ]
        assert c.anchor_entity == expected_entity
    # only the 0-hop cousins are controls
    for c in cousins:
        assert c.to_dict()["is_control"] == (c.planted_distance == 0)


def test_missing_distance_entries_are_skipped_not_fabricated():
    # No real entity was discovered at hop 2 -- plan_cousins must not invent
    # one; distance 2 simply never appears.
    entry = _entry(entities_by_distance={0: "BSTOLL-L", 1: "bstoll", 3: "web_admin"})
    cousins = corpus_bed.plan_cousins([entry], corpus_earliest=_CE, corpus_latest=_CL)
    assert 2 not in {c.planted_distance for c in cousins}
    assert {0, 1, 3} <= {c.planted_distance for c in cousins}


def test_cousin_at_2_hops_is_unreachable_when_max_depth_is_1():
    """A cousin planted 2 pivot hops from the anchor cannot be reached by an
    investigation bounded to max_depth=1 -- proving `planted_distance`
    actually gates reachability, not just a label on the record."""
    from portal.modules.security.core.bully import investigation_pivot as ip

    # anchor -> hop1 -> hop2(cousin lives here)
    chain = {"anchor-host": [("user", "hop1-user")], "hop1-user": [("resource", "hop2-res")]}
    cousin_event = {
        "_time": 1534737600.0 + 3600,
        "sourcetype": "corpus:cousin",
        "entity": "hop2-res",
    }
    own_events = {
        "anchor-host": [{"_time": 1534737600.0, "sourcetype": "st", "entity": "anchor-host"}],
        "hop1-user": [{"_time": 1534737600.0 + 1800, "sourcetype": "st", "entity": "hop1-user"}],
        "hop2-res": [cousin_event],
    }

    def execute(query: ip.PivotQuery) -> list[dict]:
        return [
            e
            for e in own_events.get(query.entity, [])
            if query.earliest <= e["_time"] <= query.latest
        ]

    def extract(row: dict) -> list[tuple[str, str]]:
        return chain.get(row.get("entity"), [])

    anchor = ip.Anchor(
        anchor_id="a-1",
        at=1534737600.0,
        entity="anchor-host",
        entity_kind="host",
        sourcetype="st",
        why="test",
        index="botsv3",
    )

    shallow = ip.investigate(anchor, ["botsv3"], execute, extract, max_depth=1)
    assert not any(e.get("sourcetype") == "corpus:cousin" for e in shallow.events)
    assert "hop2-res" not in shallow.entities_seen

    deep = ip.investigate(anchor, ["botsv3"], execute, extract, max_depth=2)
    assert any(e.get("sourcetype") == "corpus:cousin" for e in deep.events)


def test_run_reporting_only_0_hop_recovery_is_flagged_zero_hop_only():
    entry = _entry(entities_by_distance={0: "BSTOLL-L", 1: "bstoll", 2: "frothlywebcode"})
    cousins = corpus_bed.plan_cousins([entry], corpus_earliest=_CE, corpus_latest=_CL)
    # Simulate a run (I.6's shape) that only ever reaches 0-hop cousins.
    reached = {c.cousin_id for c in cousins if c.planted_distance == 0}
    planted = [(c.cousin_id, c.planted_distance) for c in cousins]
    rec = ascope.distance_recovery(planted, reached)
    d = rec.to_dict()
    assert d["zero_hop_only"] is True
    assert rec.recall_at(0) == 1.0
    assert rec.recall_at(1) == 0.0
