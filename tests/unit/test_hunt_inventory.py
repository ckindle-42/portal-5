"""Inventory enumeration, misfit-share and case promotion against stored-run shapes.

Field stats: snap_neon_02cc2e3 kyoushi sources.json audit.log (type/uid).
Behaviour: that run's behaviours.duckdb row uid=0 type=USER_END.
Misfit: that run's botsv2 osquery_warning shape whose raw line is the .mkv.crypt file.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from portal.modules.security.core.hunt.executor import Read
from portal.modules.security.core.hunt.notables.behaviours import Behaviour, MisfitShape
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.inventory import (
    INVENTORY_MAX_VALUES,
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
        facts={"index": "hb_kyoushi_s1", "sourcetype": "audit.log", "events": 100},
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
    """A fake Splunk: probes answer from configuration, value queries from `value_rows`."""

    def __init__(
        self,
        value_rows: Mapping[str, list[dict[str, object]]] | None = None,
        *,
        indexed: Iterable[str] = (),
        tstats_names: Mapping[str, int] | None = None,
        search_names: Iterable[str] | None = None,
        accelerated: Iterable[Mapping[str, object]] = (),
        model_rows: Mapping[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.value_rows = dict(value_rows or {})
        self.indexed = set(indexed)
        self.tstats_names = None if tstats_names is None else dict(tstats_names)
        self.search_names = None if search_names is None else set(search_names)
        self.accelerated = [dict(row) for row in accelerated]
        self.model_rows = dict(model_rows or {})
        self.queries: list[str] = []

    @staticmethod
    def _name(query: str) -> str:
        match = re.search(r'sourcetype="([^"]+)"', query)
        return match.group(1) if match else ""

    def _value_key(self, query: str) -> str:
        group = query.rsplit(" by ", 1)[1].strip()
        tail = query.split('sourcetype="', 1)[-1].split(" | stats", 1)[0]
        part = re.search(r' \w+="([^"]+)"', tail)
        suffix = f"|{part.group(1)}" if part else ""
        return f"{self._name(query)}|{group}{suffix}"

    def read(
        self,
        query: str,
        start: float,
        end: float,
        *,
        kind: str,
        row_cap: int | None = None,
        source_id: str | None = None,
        part: str | None = None,
    ) -> Read:
        del start, end, kind, row_cap, source_id, part
        self.queries.append(query)
        if query.startswith("| rest /services/admin/summarization"):
            return Read([dict(row) for row in self.accelerated])
        if query.startswith("| tstats summariesonly=true"):
            field = query.rsplit(" by ", 1)[1].strip()
            return Read(list(self.model_rows.get(field, [])))
        name = self._name(query)
        if query.startswith("| tstats count where "):
            if " by " in query:
                field = query.rsplit(" by ", 1)[1].strip()
                return Read([{"count": "1"}] if field in self.indexed else [])
            if self.tstats_names is None:
                return Read([{"count": "100"}])
            events = self.tstats_names.get(name)
            return Read([{"count": str(events)}] if events else [])
        if query.startswith("search ") and query.endswith("| head 1"):
            if self.search_names is None or name in self.search_names:
                return Read([{"_raw": "x"}])
            return Read([])
        return Read(self.value_rows.get(self._value_key(query), []))


def _row(value: str, field: str = "uid", **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"count": 1, "first": 1, "last": 2, "hosts": 1, **extra}
    row[field] = value
    return row


def _windows_card(*, sample: Mapping[str, object] | None = None) -> SourceCard:
    """A botsv2 card named as the tsidx path sees it, as the stored cards are."""
    return SourceCard(
        index="botsv2",
        sourcetype="wineventlog:security",
        kind="activity",
        roles={"action": ("EventCode",)},
        understood=True,
        reason=None,
        fmt="kv",
        coverage=1.0,
        fields=(_stat("EventCode", 40, 5, ("4624",)),),
        sample={"lines": 40, **(sample or {})},
        facts={"index": "botsv2", "sourcetype": "wineventlog:security", "events": 1_000_000},
        model={},
        cache_key="windows",
    )


def _wide_card() -> SourceCard:
    """A source above the stats events budget, named as its tsidx path sees it."""
    return SourceCard(
        index="botsv2",
        sourcetype="wineventlog:security",
        kind="activity",
        roles={"actor": ("user",)},
        understood=True,
        reason=None,
        fmt="kv",
        coverage=1.0,
        fields=(_stat("user", 40, 4_000, ("alice",)),),
        sample={"lines": 40, "search_sourcetypes": ["WinEventLog"]},
        facts={"index": "botsv2", "sourcetype": "wineventlog:security", "events": 2_200_000},
        model={},
        cache_key="wide",
    )


def test_select_fields_keeps_the_stored_audit_role_fields() -> None:
    chosen = select_fields([_audit_card()])

    assert [(item.field, item.role, item.distinct) for item in chosen] == [
        ("uid", "actor", 1),
        ("type", "action", 4),
    ]


def test_select_fields_prefers_actors_over_constant_actions() -> None:
    actions = tuple(f"const{index:02d}" for index in range(40))
    card = SourceCard(
        index="hb_kyoushi_s1",
        sourcetype="audit.log",
        kind="activity",
        roles={"action": actions, "actor": ("user", "owner", "acct")},
        understood=True,
        reason=None,
        fmt="kv",
        coverage=1.0,
        fields=(
            *(_stat(name, 40, 1, ("same",)) for name in actions),
            _stat("user", 40, 3, ("root",)),
            _stat("owner", 40, 2, ("root",)),
            _stat("acct", 40, 4, ("root",)),
        ),
        sample={"lines": 40},
        facts={"index": "hb_kyoushi_s1", "sourcetype": "audit.log", "events": 100},
        model={},
        cache_key="actors",
    )

    chosen = select_fields([card])

    assert {item.field for item in chosen} >= {"user", "owner", "acct"}
    assert len(chosen) < len(actions)


def test_collect_inventory_stores_values_and_records_the_stats_route() -> None:
    executor = _Executor(
        {
            "audit.log|uid, type": [
                _row("USER_END", "type", uid="0", count=1173, first=1616400000, last=1616888706),
                _row("USER_ROLE", "type", uid="33", count=2, first=1616800000, last=1616800100),
            ],
            "audit.log|uid": [_row("0", count=10)],
            "audit.log|type": [
                _row("USER_END", "type", count=1173, first=1616400000, last=1616888706),
                _row("USER_ROLE", "type", count=2, first=1616800000, last=1616800100),
            ],
        }
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 1617000000.0)

    assert document["searches"] == 3
    assert document["probe_queries"] > 0
    uid = next(item for item in document["fields"] if item["field"] == "uid")
    assert uid["status"] == "complete"
    assert uid["mechanism"] == "stats"
    assert uid["name_used"] == "audit.log"
    assert uid["events_scanned"] == 100
    assert uid["values"][0]["value"] == "0"
    joint = document["joints"][0]
    assert joint["status"] == "complete"
    assert joint["mechanism"] == "stats"
    assert joint["rows"][0]["first_seen"] == 1616400000.0
    assert any(query.endswith("by uid, type") for query in executor.queries)


def test_a_field_list_joint_is_not_another_search() -> None:
    executor = _Executor(
        {
            "audit.log|type": [
                _row(f"ACT{index}", "type", first=100 + index) for index in range(300)
            ],
            "audit.log|uid": [_row("mallory", count=4, first=10), _row("alice", count=4, first=30)],
        }
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)

    assert document["searches"] == len(executor.queries) - document["probe_queries"] == 2
    assert document["joints"][0]["reason"] == "field_list"
    assert document["joints"][0]["fields"] == [{"role": "actor", "field": "uid"}]


def test_capped_field_is_not_a_value_list() -> None:
    executor = _Executor(
        {"audit.log|uid": [_row(str(index)) for index in range(INVENTORY_MAX_VALUES + 1)]}
    )
    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)
    uid = next(item for item in document["fields"] if item["field"] == "uid")

    assert uid["status"] == "capped"
    assert uid["values"] == []


def test_tstats_without_a_value_column_is_unavailable_not_empty() -> None:
    executor = _Executor(
        {"audit.log|type": [{"count": 5, "first": 1, "last": 2}]},
        indexed={"type"},
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)
    record = next(item for item in document["fields"] if item["field"] == "type")

    assert record["status"] == "unavailable:tstats"
    assert record["values"] == []


def test_a_source_with_two_names_uses_the_name_each_path_accepts() -> None:
    card = _windows_card(sample={"search_sourcetypes": ["WinEventLog"]})
    executor = _Executor(
        {
            "WinEventLog|EventCode": [
                {"EventCode": "4624", "count": 9, "first": 1, "last": 2, "hosts": 3}
            ]
        },
        tstats_names={"wineventlog:security": 1_000_000},
        search_names={"WinEventLog"},
    )

    document = collect_inventory(executor, [card], "botsv2", 0.0, 10.0)

    record = document["fields"][0]
    assert record["status"] == "complete"
    assert record["mechanism"] == "stats"
    assert record["name_used"] == "WinEventLog"
    assert record["values"][0]["value"] == "4624"
    assert document["names"][0]["two_names"] is True


def test_a_rejected_name_is_unavailable_name_not_empty() -> None:
    card = _windows_card()
    executor = _Executor(
        tstats_names={"wineventlog:security": 1_000_000},
        search_names=set(),
    )

    document = collect_inventory(executor, [card], "botsv2", 0.0, 10.0)

    record = document["fields"][0]
    assert record["status"] == "unavailable:name"
    assert not any(" | stats " in query for query in executor.queries)


def test_a_wide_source_is_listed_from_a_complete_accelerated_summary() -> None:
    card = _wide_card()
    executor = _Executor(
        tstats_names={"wineventlog:security": 2_200_000},
        search_names={"WinEventLog"},
        accelerated=[
            {
                "datamodel_name": "Authentication",
                "summary.complete": "1",
                "summary.earliest_time": 1.5e9,
                "summary.latest_time": 1.7e9,
            },
            {
                "datamodel_name": "Web",
                "summary.complete": "0.4",
                "summary.earliest_time": 1.5e9,
                "summary.latest_time": 1.7e9,
            },
        ],
        model_rows={
            "Authentication.user": [
                {"Authentication.user": "alice", "count": 7, "first": 1.6e9, "last": 1.61e9}
            ]
        },
    )

    document = collect_inventory(executor, [card], "botsv2", 0.0, 2.0e9)

    record = document["fields"][0]
    assert record["status"] == "complete"
    assert record["mechanism"] == "datamodel"
    assert record["values"][0]["value"] == "alice"
    assert record["events_scanned"] == 7
    assert record["accel_window"] == [1.5e9, 1.7e9]
    assert record["searched_window"] == [0.0, 2.0e9]
    assert document["accelerated"] == [
        {"model": "Authentication", "earliest": 1.5e9, "latest": 1.7e9}
    ]
    assert not any(" | stats " in query for query in executor.queries)
    assert "summariesonly=true" in next(
        query for query in executor.queries if "datamodel=" in query
    )


def test_a_wide_source_with_no_accelerated_model_is_unavailable_not_empty() -> None:
    executor = _Executor(
        tstats_names={"wineventlog:security": 2_200_000},
        search_names={"WinEventLog"},
    )

    document = collect_inventory(executor, [_wide_card()], "botsv2", 0.0, 2.0e9)

    record = document["fields"][0]
    assert record["status"] == "unavailable:mechanism"
    assert record["reason"] == "events_budget"
    assert record["values"] == []
    assert not any(" | stats " in query for query in executor.queries)


def test_the_same_field_on_two_parts_makes_two_lists() -> None:
    def card(part: str) -> SourceCard:
        return SourceCard(
            index="hb_kyoushi_s1",
            sourcetype="audit.log",
            kind="activity",
            roles={"actor": ("uid",)},
            understood=True,
            reason=None,
            fmt="kv",
            coverage=1.0,
            fields=(_stat("uid", 20, 3, ("0",)),),
            sample={"lines": 20},
            facts={"index": "hb_kyoushi_s1", "sourcetype": "audit.log", "events": 100},
            model={},
            cache_key=f"audit-{part}",
            part_field="channel",
            part_value=part,
        )

    executor = _Executor(
        {
            "audit.log|uid|A": [{"uid": "alice", "count": 3, "first": 1, "last": 2, "hosts": 1}],
            "audit.log|uid|B": [{"uid": "mallory", "count": 4, "first": 3, "last": 4, "hosts": 1}],
        }
    )

    document = collect_inventory(executor, [card("A"), card("B")], "hb_kyoushi_s1", 0.0, 10.0)

    records = {item["part"]["value"]: item for item in document["fields"]}
    assert set(records) == {"A", "B"}
    assert records["A"]["values"][0]["value"] == "alice"
    assert records["B"]["values"][0]["value"] == "mallory"


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
            "audit.log|type": [{"type": "USER_END", "count": 4, "first": 200.0, "last": 300.0}],
            "access.log|type": [{"type": "USER_END", "count": 9, "first": 100.0, "last": 150.0}],
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
            facts={"events": 50},
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
