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
    CaseUnit,
    _case_groups,
    _flow_units,
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
        declared: Iterable[str] = (),
        absent: Iterable[str] = (),
        hosts: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        self.value_rows = dict(value_rows or {})
        self.indexed = set(indexed)
        self.tstats_names = None if tstats_names is None else dict(tstats_names)
        self.search_names = None if search_names is None else set(search_names)
        self.accelerated = [dict(row) for row in accelerated]
        self.model_rows = dict(model_rows or {})
        self.declared = set(declared)
        self.absent = set(absent)
        self.hosts = {name: list(names) for name, names in (hosts or {}).items()}
        self.queries: list[str] = []

    @staticmethod
    def _name(query: str) -> str:
        match = re.search(r'sourcetype="([^"]+)"', query)
        return match.group(1) if match else ""

    @staticmethod
    def _value_key(query: str) -> str:
        route, _sep, by = query.partition(" by ")
        part = re.search(r' \w+="([^"]+)"', route.split('sourcetype="', 1)[-1])
        rare = "|rare" if " sort 0 count " in query else ""
        return (
            f"{_Executor._name(query)}|{by.split(' | ', 1)[0].strip()}"
            + (f"|{part.group(1)}" if part else "")
            + rare
        )

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
        if query.startswith("| rest /servicesNS/-/-/configs/conf-fields"):
            return Read([{"title": name, "INDEXED": "1"} for name in sorted(self.declared)])
        if query.startswith("| tstats summariesonly=true"):
            field = query.rsplit(" by ", 1)[1].split(" | ", 1)[0].strip()
            return Read(list(self.model_rows.get(field, [])))
        name = self._name(query)
        if query.startswith("| tstats count where ") and query.endswith(" by host"):
            return Read([{"host": host, "count": "1"} for host in self.hosts.get(name, [])])
        if query.startswith("| tstats count where "):
            if " by " in query:
                field = query.split(" by ", 1)[1].strip()
                return Read([{"count": "1"}] if field in self.indexed else [])
            if self.tstats_names is None:
                return Read([{"count": "100"}])
            events = self.tstats_names.get(name)
            return Read([{"count": str(events)}] if events else [])
        if "| stats count as sampled" in query:
            return Read([self._sampled(query)])
        if query.startswith("search ") and query.endswith("| head 1"):
            if self.search_names is None or name in self.search_names:
                return Read([{"_raw": "x"}])
            return Read([])
        return Read(self.value_rows.get(self._value_key(query), []))

    def _sampled(self, query: str) -> dict[str, object]:
        row: dict[str, object] = {"sampled": "1000"}
        for index, field in _count_aliases(query):
            row[f"p{index}"] = "0" if field in self.absent else "1"
        return row


def _count_aliases(query: str) -> list[tuple[int, str]]:
    return [
        (int(number), field) for field, number in re.findall(r"count\(([^)]+)\) as p(\d+)", query)
    ]


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
        facts={
            "index": "botsv2",
            "sourcetype": "wineventlog:security",
            "events": 2_200_000,
            "first": 1.616e9,
            "last": 1.642e9,
        },
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
    assert any(" by uid, type " in query for query in executor.queries)


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


def test_a_capped_field_keeps_the_volume_ends_and_its_share() -> None:
    rows = [_row(str(index), count=index + 1) for index in range(INVENTORY_MAX_VALUES + 1)]
    executor = _Executor(
        {
            "audit.log|uid": rows,
            "audit.log|uid|rare": [
                _row("rare-a", count=1, first=7, last=8),
                _row("rare-b", count=1, first=9, last=9),
                _row("rare-c", count=2, first=11, last=12),
            ],
        }
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)
    uid = next(item for item in document["fields"] if item["field"] == "uid")

    assert uid["status"] == "capped"
    assert len(uid["values"]) == INVENTORY_MAX_VALUES
    kept = {item["value"]: item for item in uid["values"]}
    assert {"rare-a", "rare-b", "rare-c"} <= set(kept)
    assert kept["rare-a"]["first_seen"] == 7.0
    assert uid["capped_share"] == round(INVENTORY_MAX_VALUES / (INVENTORY_MAX_VALUES + 1), 6)


def test_tstats_without_a_value_column_is_unavailable_not_empty() -> None:
    executor = _Executor(
        {"audit.log|type": [{"count": 5, "first": 1, "last": 2}]},
        indexed={"type"},
    )

    document = collect_inventory(executor, [_audit_card()], "hb_kyoushi_s1", 0.0, 10.0)
    record = next(item for item in document["fields"] if item["field"] == "type")

    assert record["status"] == "unavailable:tstats"
    assert record["values"] == []


def test_the_estate_vocabulary_replaces_parse_local_names_as_lists() -> None:
    card = SourceCard(
        index="ix",
        sourcetype="access_combined",
        kind="activity",
        roles={"actor": ("program",), "action": ("template",), "object": ("v1", "v2")},
        understood=True,
        reason=None,
        fmt="template",
        coverage=1.0,
        fields=(
            _stat("program", 40, 1, ("apache",)),
            _stat("template", 40, 2, ("a b",)),
            _stat("v1", 40, 4, ("x",)),
            _stat("v2", 40, 9, ("y",)),
        ),
        sample={"lines": 40},
        facts={"index": "ix", "sourcetype": "access_combined", "events": 500},
        model={},
        cache_key="access",
    )
    executor = _Executor(
        {
            "access_combined|c_ip": [_row("10.1.1.1", "c_ip", count=9), _row("10.1.1.2", "c_ip")],
            "access_combined|acct": [_row("root", "acct", count=3)],
        },
        indexed={"c_ip", "acct"},
        declared={"c_ip", "acct"},
        absent={"program", "template", "v1", "v2"},
    )

    document = collect_inventory(executor, [card], "ix", 0.0, 10.0)

    lists = {item["field"]: item for item in document["fields"]}
    assert lists["c_ip"]["mechanism"] == "tstats"
    assert lists["c_ip"]["status"] == "complete"
    assert [row["value"] for row in lists["acct"]["values"]] == ["root"]
    assert lists["template"]["status"] == "parse_only"
    assert lists["template"]["values"] == []
    assert {item["status"] for item in document["fields"]} == {"complete", "parse_only"}
    assert not any(" by template" in query or " by v1" in query for query in executor.queries)
    assert document["vocabulary"] == 2


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


def test_rung_1_lists_from_a_covering_summary_before_the_indexed_route() -> None:
    """The real endpoint payload: accelerators are keyed `title`/`summary.id`, not `datamodel_name`."""
    card = _wide_card()
    executor = _Executor(
        tstats_names={"wineventlog:security": 2_200_000},
        search_names={"WinEventLog"},
        indexed={"user"},
        accelerated=[
            {
                "title": "tstats:DM_Splunk_SA_CIM_Authentication",
                "summary.id": "DM_Splunk_SA_CIM_Authentication",
                "summary.complete": "1",
                "summary.earliest_time": 1.4e9,
                "summary.latest_time": 2.0e9,
            },
            {
                "title": "tstats:DM_Splunk_SA_CIM_Web",
                "summary.id": "DM_Splunk_SA_CIM_Web",
                "summary.complete": "0.4",
                "summary.earliest_time": 1.4e9,
                "summary.latest_time": 2.0e9,
            },
            {
                "title": "tstats:DM_Splunk_SA_CIM_Network_Resolution",
                "summary.id": "DM_Splunk_SA_CIM_Network_Resolution",
                "summary.complete": "1",
                "summary.earliest_time": 1.0e9,
                "summary.latest_time": 1.2e9,
            },
        ],
        model_rows={
            "Authentication.user": [
                {"Authentication.user": "alice", "count": 7, "first": 1.6e9, "last": 1.61e9}
            ]
        },
    )

    document = collect_inventory(executor, [card], "botsv2", 0.0, 1_790_000_000.0)

    record = document["fields"][0]
    assert record["status"] == "complete"
    assert record["mechanism"] == "accelerated"
    assert record["events_scope"] == "summary"
    assert record["values"][0]["value"] == "alice"
    assert record["events_scanned"] == 7
    assert record["accel_window"] == [1.4e9, 2.0e9]
    # The coverage test is the card's own span (1.616e9-1.642e9), not the query's all-time bound.
    assert record["searched_window"] == [0.0, 1_790_000_000.0]
    # Web is incomplete and Network_Resolution's window ends before the source begins.
    assert document["accelerated"] == [
        {"model": "Authentication", "earliest": 1.4e9, "latest": 2.0e9}
    ]
    assert not any("dc(host) as hosts" in query for query in executor.queries)
    assert "summariesonly=true" in next(
        query for query in executor.queries if "datamodel=" in query
    )
    assert document["model_probes"] == 1
    assert not any(" by user" in query for query in executor.queries)


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
    assert not any("dc(host) as hosts" in query for query in executor.queries)


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
        },
        indexed=("type",),
        hosts={"audit.log": ["webserver"], "access.log": ["webserver"]},
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
    # the tsidx probe names the host both endpoints see the value on
    assert document["flows"][0]["host"] == "webserver"
    assert document["flows"][0]["host_proven"] is True
    assert any(query.endswith(" by host") for query in executor.queries)


def test_a_duplicate_ingest_pair_is_never_a_flow() -> None:
    """The stored control estate ingests the same mail log twice: one shape, one aggregate."""
    rows = [{"user": "<amanda.watson>", "count": 893, "first": 1642139896.0, "last": 1642445389.0}]

    def mail_card(name: str) -> SourceCard:
        return SourceCard(
            index="hb_ait_santos",
            sourcetype=name,
            kind="activity",
            roles={"action": ("method",), "actor": ("user",)},
            understood=True,
            reason=None,
            fmt="kv",
            coverage=1.0,
            fields=(_stat("user", 893, 17, ("<amanda.watson>",)), _stat("method", 893, 1, ("<",))),
            sample={"lines": 893},
            facts={"events": rows[0]["count"]},
            model={},
            cache_key=name,
        )

    document = collect_inventory(
        _Executor({f"{name}|user": rows for name in ("mail.info", "mail.log")}),
        [mail_card("mail.info"), mail_card("mail.log")],
        "hb_ait_santos",
        0.0,
        1642500000.0,
    )

    assert document["flows"] == []
    assert document["flow_skips"] == {"duplicate": 1}


def test_flow_links_two_sources_sharing_a_value_with_adjacent_roles() -> None:
    identity = {
        "ix:web": {"roles": {"actor": ["v1"], "from": ["v1"]}},
        "ix:auth": {"roles": {"to": ["uid"], "actor": ["uid"]}},
    }
    paths = {"10.1.1.1": {"address:10.1.1.1": {"ix:web", "ix:auth"}}}
    steps = [
        {"source_id": "ix:web", "field": "v1", "first_seen": 100.0, "last_seen": 200.0},
        {"source_id": "ix:auth", "field": "uid", "first_seen": 30_000.0, "last_seen": 30_100.0},
    ]
    flow = {"value": "10.1.1.1", "steps": steps}

    units, skipped = _flow_units([flow], identity, paths)
    assert skipped == 0
    assert units[0].roles == ("from", "to")
    episodes = [
        CaseUnit("web", "episode", "address:10.1.1.1", "10.1.1.1", "ix:web", "h1", 100.0, 200.0),
        CaseUnit(
            "auth", "episode", "address:10.1.1.1", "10.1.1.1", "ix:auth", "h1", 30_000.0, 30_100.0
        ),
    ]
    groups, counters = _case_groups([*episodes, *units])

    assert len(groups) == 1
    assert counters["links"] == 2
    # the same role at both ends is ambient data, not a transition
    same = [{"source_id": "ix:web", "field": "v1"}, {"source_id": "ix:auth", "field": "uid"}]
    assert _flow_units([{"value": "10.1.1.1", "steps": same}], identity, paths) == ([], 1)


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
