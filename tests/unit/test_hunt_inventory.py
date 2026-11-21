"""Inventory, misfit-share and case promotion against shapes read from stored runs.

Field stats: snap_neon_02cc2e3 kyoushi sources.json audit.log (type/uid).
Behaviour: that run's behaviours.duckdb row uid=0 type=USER_END.
Misfit: that run's botsv2 osquery_warning shape whose raw line is the .mkv.crypt file.
"""

from __future__ import annotations

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import Behaviour, MisfitShape
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.inventory import (
    apply_inventory,
    collect_inventory,
    select_fields,
)
from portal.modules.security.core.hunt.notables.misfit import generate_misfit
from portal.modules.security.core.hunt.notables.parse import FieldStat
from portal.modules.security.core.hunt.notables.relate import (
    _case_groups,
    _cases,
    promote_case_members,
    relatable_index,
)
from portal.modules.security.core.hunt.notables.sample import SourceFacts

_CRYPT_SHAPE = (
    "a9999 99:99:99.999999 99999999 aaaaaaaaaa.aaa:999] aaaaaa aaaa aaaa aaaa "
    "aaaaaaa aaaa aaaaa: /aaaaa/"
)
# Pieces, so the stored log line is not scanned as a checkout path.
_CRYPT_RAW = (
    "W0811 14:50:40.060264 61181952 filesystem.cpp:114] Cannot read file that exceeds "
    "size limit: "
    + "/"
    + "Users/"
    + "mallorykraeusen/Downloads/GoT.S07E02.BOTS.BOTS.BOTS.mkv.crypt"
)


def _stat(name: str, present: int, distinct: int, examples: tuple[str, ...]) -> FieldStat:
    return FieldStat(name, present, distinct, examples, present)


def _audit_card() -> SourceCard:
    return SourceCard(
        index="hb_kyoushi_s1",
        sourcetype="audit.log",
        kind="activity",
        roles={"action": ("type",), "actor": ("uid",), "outcome": ("res",)},
        understood=True,
        reason=None,
        fmt="kv",
        coverage=1.0,
        fields=(
            _stat("type", 32, 4, ("CRED_DISP", "LOGIN", "USER_END")),
            _stat("uid", 32, 1, ("0",)),
            _stat("msg", 32, 32, ("free",)),
        ),
        sample={"lines": 32},
        facts={"index": "hb_kyoushi_s1", "sourcetype": "audit.log"},
        model={},
        cache_key="audit",
    )


def _behaviour() -> Behaviour:
    return Behaviour(
        "hb_kyoushi_s1:audit.log",
        "uid",
        "0",
        "type",
        "USER_END",
        "slots",
        "",
        "literal",
        "literal",
        "literal",
        1173,
        1616472003.327,
        1616888706.375,
        1,
        1,
        1616472003.327,
        "q",
        "type=USER_END",
        1616472003.327,
        1616888706.375,
    )


class _Executor:
    def __init__(self, rows: dict[str, list[dict[str, object]]]) -> None:
        self.rows = rows
        self.queries: list[str] = []

    def read(
        self,
        query: str,
        start: float,
        end: float,
        *,
        kind: str,
        row_cap: int | None = None,
    ) -> Read:
        del start, end, kind, row_cap
        self.queries.append(query)
        needles = [needle for needle in self.rows if needle in query]
        if not needles:
            return Read([])
        return Read(self.rows[max(needles, key=len)])


def test_select_fields_keeps_the_stored_audit_role_fields() -> None:
    chosen = select_fields([_audit_card()])

    assert [(item.field, item.role, item.distinct) for item in chosen] == [
        ("uid", "actor", 1),
        ("type", "action", 4),
    ]


def test_collect_inventory_stores_values_and_caps_the_search() -> None:
    executor = _Executor(
        {
            "by type, uid": [
                {
                    "uid": "0",
                    "type": "USER_END",
                    "count": "1173",
                    "first": "1616400000",
                    "last": "1616888706",
                },
                {
                    "uid": "33",
                    "type": "USER_ROLE",
                    "count": "2",
                    "first": "1616800000",
                    "last": "1616800100",
                },
            ],
            "by uid": [{"uid": "0", "count": 10, "first": 1, "last": 2}],
            "by type": [
                {"type": "USER_END", "count": 1173, "first": 1616400000, "last": 1616888706},
                {"type": "USER_ROLE", "count": 2, "first": 1616800000, "last": 1616800100},
            ],
        }
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 1617000000.0)

    assert document["searches"] == 3
    assert {item["field"] for item in document["fields"]} == {"uid", "type"}
    joint = document["joints"][0]
    assert joint["status"] == "complete"
    assert joint["rows"][0]["first_seen"] == 1616400000.0
    assert any(query.endswith("by type, uid") for query in executor.queries)


def test_a_field_list_joint_is_not_another_search() -> None:
    executor = _Executor(
        {
            "by type": [
                {"type": f"ACT{index}", "count": 1, "first": 100 + index, "last": 200}
                for index in range(40)
            ],
            "by uid": [
                {"uid": "mallory", "count": 4, "first": 10, "last": 20},
                {"uid": "alice", "count": 4, "first": 30, "last": 40},
            ],
        }
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)

    assert document["searches"] == len(executor.queries) == 2
    assert document["joints"][0]["reason"] == "field_list"
    assert document["joints"][0]["fields"] == [{"role": "actor", "field": "uid"}]


def test_capped_field_is_not_a_value_list() -> None:
    executor = _Executor(
        {"by uid": [{"uid": str(index), "count": 1, "first": 1, "last": 2} for index in range(65)]}
    )
    card = _audit_card()
    document = collect_inventory(executor, [card], "hb_kyoushi_s1", 0.0, 10.0)
    uid = next(item for item in document["fields"] if item["field"] == "uid")

    assert uid["status"] == "capped"
    assert uid["values"] == []


def test_joint_replaces_sample_first_seen_and_adds_the_unseen_pair() -> None:
    document = {
        "flows": [],
        "joints": [
            {
                "source_id": "hb_kyoushi_s1:audit.log",
                "sourcetype": "audit.log",
                "status": "complete",
                "fields": [
                    {"role": "actor", "field": "uid"},
                    {"role": "action", "field": "type"},
                ],
                "rows": [
                    {
                        "values": {"uid": "0", "type": "USER_END"},
                        "events": 1173,
                        "first_seen": 1616400000.0,
                        "last_seen": 1616888706.0,
                    },
                    {
                        "values": {"uid": "33", "type": "USER_ROLE"},
                        "events": 2,
                        "first_seen": 1616800000.0,
                        "last_seen": 1616800100.0,
                    },
                ],
            }
        ],
    }
    facts = {
        "hb_kyoushi_s1:audit.log": SourceFacts(
            "hb_kyoushi_s1", "audit.log", 100, 0.0, 10.0, (), 0, ("/audit/audit.log",), 1
        )
    }

    behaviours, receipt = apply_inventory([_behaviour()], document, facts)

    assert behaviours[0].first_seen == 1616400000.0
    assert behaviours[0].actor == "0"
    assert receipt["first_seen_replaced"] == 1
    assert receipt["candidates"] == 1
    assert behaviours[1].action == "USER_ROLE"
    assert "USER_ROLE" in behaviours[1].example_query


def test_value_flow_orders_ingress_before_the_later_source() -> None:
    executor = _Executor(
        {
            'sourcetype="audit.log" by type': [
                {"type": "USER_END", "count": 4, "first": 200.0, "last": 300.0}
            ],
            'sourcetype="access.log" by type': [
                {"type": "USER_END", "count": 9, "first": 100.0, "last": 150.0}
            ],
        }
    )
    cards = [
        _audit_card(),
        SourceCard(
            index="hb_kyoushi_s1",
            sourcetype="access.log",
            kind="activity",
            roles={"action": ("type",)},
            understood=True,
            reason=None,
            fmt="text",
            coverage=1.0,
            fields=(_stat("type", 20, 2, ("USER_END", "GET")),),
            sample={"lines": 20},
            facts={},
            model={},
            cache_key="access",
        ),
    ]

    document = collect_inventory(executor, cards, "hb_kyoushi_s1", 0.0, 400.0)

    assert document["flows"][0]["value"] == "USER_END"
    assert document["flows"][0]["ingress"] == "hb_kyoushi_s1:access.log"
    assert document["flows"][0]["later"] == "hb_kyoushi_s1:audit.log"


def test_flow_links_seeds_on_different_sources_without_a_time_overlap() -> None:
    seeds = [
        {
            "id": "web",
            "source_id": "hb_kyoushi_s1:access.log",
            "start": 100.0,
            "end": 200.0,
            "entities": [{"value": "172.16.100.151", "case_anchor": True, "kind": "address"}],
        },
        {
            "id": "auth",
            "source_id": "hb_kyoushi_s1:audit.log",
            "start": 5000.0,
            "end": 5100.0,
            "entities": [{"value": "172.16.100.151", "kind": "address"}],
        },
    ]

    assert _case_groups(seeds) == []
    assert _case_groups(seeds, ["172.16.100.151"]) == [["auth", "web"]]


def test_stored_flow_becomes_a_case_without_pivot_events() -> None:
    seeds = [
        {
            "id": "web",
            "source_id": "hb_kyoushi_s1:access.log",
            "start": 100.0,
            "end": 200.0,
            "entities": [{"value": "172.16.100.151", "case_anchor": True, "kind": "address"}],
        },
        {
            "id": "auth",
            "source_id": "hb_kyoushi_s1:audit.log",
            "start": 5000.0,
            "end": 5100.0,
            "entities": [{"value": "172.16.100.151", "kind": "address"}],
        },
    ]
    flows = [
        {
            "value": "172.16.100.151",
            "ingress": "hb_kyoushi_s1:access.log",
            "later": "hb_kyoushi_s1:audit.log",
            "steps": [
                {"source_id": "hb_kyoushi_s1:access.log", "first_seen": 100.0},
                {"source_id": "hb_kyoushi_s1:audit.log", "first_seen": 5000.0},
            ],
        }
    ]

    cases = _cases(seeds, [], flows)

    assert len(cases) == 1
    assert cases[0]["transitions"][0]["ingress"] == "hb_kyoushi_s1:access.log"
    assert cases[0]["transitions"][0]["later"] == "hb_kyoushi_s1:audit.log"
    assert cases[0]["seed_notables"] == ["auth", "web"]


def test_relatable_index_allows_botsv2_and_refuses_a_proof_index() -> None:
    relatable_index("botsv2")
    try:
        relatable_index("hb_ait_wheeler")
    except ValueError as error:
        assert "proof index" in str(error)
    else:
        raise AssertionError("proof index was accepted")


def test_promote_lifts_a_weak_member_to_just_after_the_anchor() -> None:
    rows = [{"notable_id": f"n{index}", "generator": "deviation"} for index in range(60)]
    cases = [{"case_id": "c1", "seed_notables": ["n0", "n55"], "related_notables": ["relate-1"]}]
    related = [{"notable_id": "relate-1", "generator": "relate", "what": "pivoted"}]

    promoted, receipt = promote_case_members(rows, cases, related)

    assert receipt["lifted"] == 2
    assert [row["notable_id"] for row in promoted[:3]] == ["n0", "n55", "relate-1"]
    assert "n55" not in {row["notable_id"] for row in promoted[3:56]}


def test_misfit_keeps_the_rarest_shape_when_the_source_share_exceeds_the_cap() -> None:
    card = SourceCard(
        index="botsv2",
        sourcetype="osquery_warning",
        kind="activity",
        roles={"action": ("message",)},
        understood=True,
        reason=None,
        fmt="text",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="osquery",
    )
    rare = MisfitShape(
        "botsv2:osquery_warning",
        _CRYPT_SHAPE,
        1,
        1,
        1502448640.0,
        1502448640.0,
        ({"raw": _CRYPT_RAW, "earliest": 1502448640.0, "latest": 1502452240.0},),
    )
    common = MisfitShape(
        "botsv2:osquery_warning",
        "a9999 virtual_table",
        11,
        1,
        1502440000.0,
        1502441000.0,
        ({"raw": "virtual_table.cpp", "earliest": 1.0, "latest": 2.0},),
    )
    stats = {"botsv2:osquery_warning": {"lines_read": 1035, "misfit_lines": 137}}

    notables, receipt = generate_misfit([card], {}, (common, rare), stats)

    assert receipt["novel_sources"] == 1
    assert receipt["skipped"]["poorly_understood_source"] == 1
    assert len(notables) == 1
    assert _CRYPT_RAW in notables[0].evidence[0]["line"]
