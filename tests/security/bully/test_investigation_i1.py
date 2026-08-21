"""TASK_BULLY_INVESTIGATION_V1 (I.1): anchor-pivot investigation engine.

Staged as a BOTSv3-shaped chain: different entities per stage, sharing no
identifier, buried in background noise. `investigate()` must reconstruct the
whole chain from a single symptom anchor via recursive, bounded, time-scoped
entity pivoting -- not a flat scan.
"""

from __future__ import annotations

import random

from portal.modules.security.core.bully import investigation_pivot as ip

# Reference epoch: 20 Aug 2018, matching BOTSv3's real single-day scenario.
DAY_START = 1534737600.0  # 2018-08-20 00:00:00 UTC
SYMPTOM_AT = DAY_START + 15 * 3600 + 45 * 60  # 15:45

# The documented BOTSv3-shaped pivot chain: stages share NO identifier.
# (offset_seconds, index, sourcetype, entity, entity_kind, refers_to [(kind, entity), ...])
CHAIN = [
    (9 * 3600, "botsv3", "aws:cloudtrail", "web_admin", "user", []),
    (9 * 3600 + 300, "botsv3", "aws:cloudtrail", "null_admin", "user", []),
    # one cloudtrail event names both principals AND the bucket it touched --
    # this is the hop that links web_admin/null_admin/frothlywebcode together.
    (
        9 * 3600 + 600,
        "botsv3",
        "aws:cloudtrail",
        "frothlywebcode",
        "resource",
        [("user", "null_admin"), ("user", "web_admin")],
    ),
    (
        10 * 3600,
        "botsv3",
        "xmlwineventlog:sysmon",
        "bstoll",
        "user",
        [("resource", "frothlywebcode")],
    ),
    (10 * 3600 + 120, "botsv3", "xmlwineventlog:sysmon", "BSTOLL-L", "host", [("user", "bstoll")]),
    (11 * 3600, "botsv3", "stream:smtp", "BSTOLL-L", "host", []),
    (15 * 3600 + 45 * 60, "botsv3", "symantec:ep:security:file", "BSTOLL-L", "host", []),
]

EXPECTED_STAGE_ENTITIES = (
    "BSTOLL-L",
    "bstoll",
    "web_admin",
    "null_admin",
    "frothlywebcode",
)


def _build_events() -> list[dict]:
    events = []
    for offset, index, st, entity, kind, _refers in CHAIN:
        events.append(
            {
                "_time": DAY_START + offset,
                "index": index,
                "sourcetype": st,
                "entity": entity,
                "entity_kind": kind,
            }
        )
    rng = random.Random(42)
    background_entities = [f"bg-user-{i}" for i in range(50)]
    background_sourcetypes = ["stream:dns", "wineventlog:security", "perfmon:cpu"]
    for _i in range(400):
        events.append(
            {
                "_time": DAY_START + rng.uniform(0, 24 * 3600),
                "index": "botsv3",
                "sourcetype": rng.choice(background_sourcetypes),
                "entity": rng.choice(background_entities),
                "entity_kind": "user",
            }
        )
    return events


EVENTS = _build_events()


def _execute_factory(events: list[dict]):
    def execute(query: ip.PivotQuery) -> list[dict]:
        return [
            e
            for e in events
            if e["index"] == query.index
            and e["entity"] == query.entity
            and query.earliest <= e["_time"] <= query.latest
        ]

    return execute


_BY_ENTITY_STAGE: dict[tuple[str, str], list[tuple[str, str]]] = {
    (entity, st): refers_to for _off, _idx, st, entity, _kind, refers_to in CHAIN
}
_CHILDREN_OF: dict[str, list[tuple[str, str]]] = {}
for _off, _idx, _st, _entity, _kind, _refers_to in CHAIN:
    for _rkind, _rentity in _refers_to:
        _CHILDREN_OF.setdefault(_rentity, []).append((_kind, _entity))


def _extract_entities(row: dict) -> list[tuple[str, str]]:
    """Simulates real field extraction discovering related entities in the
    same record: both the entities this stage was pivoted FROM (backward)
    and any stage pivoted FROM this entity (forward)."""
    out: list[tuple[str, str]] = []
    out.extend(_BY_ENTITY_STAGE.get((row.get("entity"), row.get("sourcetype")), []))
    out.extend(_CHILDREN_OF.get(row.get("entity"), []))
    return out


SYMPTOM_ANCHOR = ip.Anchor(
    anchor_id="a-monero-1545",
    at=SYMPTOM_AT,
    entity="BSTOLL-L",
    entity_kind="host",
    sourcetype="symantec:ep:security:file",
    why="monero_miner_detection",
    index="botsv3",
)


def test_reconstructs_full_chain_from_symptom_anchor():
    inv = ip.investigate(
        SYMPTOM_ANCHOR,
        ["botsv3"],
        _execute_factory(EVENTS),
        _extract_entities,
    )
    report = ip.reach_report(inv, EXPECTED_STAGE_ENTITIES)
    assert report.reach_recall == 1.0, report.missed
    assert not report.truncated
    assert report.n_sourcetypes >= 4


def test_recursion_is_load_bearing_seeded_violation():
    """Seeded violation: with max_depth=1, the recursion cannot reach
    web_admin's downstream resources -- proving depth beyond 1 does real
    work, not merely widening the same query."""
    inv = ip.investigate(
        SYMPTOM_ANCHOR,
        ["botsv3"],
        _execute_factory(EVENTS),
        _extract_entities,
        max_depth=1,
    )
    seen = set(inv.entities_seen)
    assert "null_admin" not in seen or "frothlywebcode" not in seen


def test_event_outside_corpus_range_is_unreachable():
    cousin_events = list(EVENTS) + [
        {
            "_time": SYMPTOM_AT + 8 * 365 * 24 * 3600,  # ~8 years later
            "index": "botsv3",
            "sourcetype": "corpus:cousin",
            "entity": "BSTOLL-L",
            "entity_kind": "host",
        }
    ]
    inv = ip.investigate(
        SYMPTOM_ANCHOR,
        ["botsv3"],
        _execute_factory(cousin_events),
        _extract_entities,
        corpus_earliest=DAY_START,
        corpus_latest=DAY_START + 24 * 3600,
    )
    assert all(e["sourcetype"] != "corpus:cousin" for e in inv.events)


def test_repeated_scope_not_requeried():
    calls = []

    def counting_execute(query: ip.PivotQuery) -> list[dict]:
        calls.append(query)
        return _execute_factory(EVENTS)(query)

    ip.investigate(SYMPTOM_ANCHOR, ["botsv3"], counting_execute, _extract_entities)
    scopes = [(q.index, q.entity, int(q.earliest), int(q.latest)) for q in calls]
    assert len(scopes) == len(set(scopes))


def test_caps_populate_truncated_reasons():
    inv = ip.investigate(
        SYMPTOM_ANCHOR,
        ["botsv3"],
        _execute_factory(EVENTS),
        _extract_entities,
        max_queries=1,
    )
    assert inv.truncated_reasons
    assert any("max_queries" in r for r in inv.truncated_reasons)
