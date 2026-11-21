from __future__ import annotations

from typing import Any

from portal.modules.security.core.hunt.notables.relate import (
    CaseUnit,
    _case_from_members,
    _case_groups,
    _entities,
    _entity_supported,
    _identity_role,
    _query,
    _route,
    _seed_records,
    promote_case_members,
)

START = 1_700_000_000.0

IDENTITY = {
    "idx:access": {"fmt": "template", "actor_field": "v1", "objects": ["v2"]},
    "idx:auth": {"fmt": "template", "actor_field": "program", "objects": ["v1", "v2"]},
    "idx:audit": {"fmt": "kv", "actor_field": "uid", "objects": []},
}


def test_identity_role_is_object_for_program_actor_sources() -> None:
    assert _identity_role({"actor_field": "program"}) == "object"
    assert _identity_role({"actor_field": "uid"}) == "actor"
    assert _identity_role({"actor_field": ""}) == "object"


def test_entities_drop_program_names_but_keep_object_identity() -> None:
    entities = _entities(
        {
            "source_id": "idx:auth",
            "entities": [
                {"role": "actor", "value": "systemd-logind"},
                {"role": "object", "value": "msperl"},
            ],
        },
        IDENTITY,
        {},
    )
    values = [entity["value"] for entity in entities]
    assert "msperl" in values
    assert "systemd-logind" not in values


def test_entities_drop_timestamps() -> None:
    entities = _entities(
        {
            "source_id": "idx:access",
            "entities": [
                {"role": "actor", "value": "[23/Mar/2021:21:12:56 +0000]"},
            ],
        },
        IDENTITY,
        {},
    )
    assert entities == []


def test_entities_keep_short_uid_via_field_query() -> None:
    entities = _entities(
        {
            "source_id": "idx:audit",
            "entities": [
                {"role": "actor", "value": "33"},
                {"role": "action", "value": "USER_AUTH"},
            ],
        },
        IDENTITY,
        {},
    )
    by_value = {entity["value"]: entity for entity in entities}
    assert by_value["33"]["field"] == "uid"
    assert by_value["33"]["kind"] == "user"
    # USER_AUTH is the action role, not the identity role, so it is not a pivot
    assert "USER_AUTH" not in by_value


def test_invalid_ipv4_text_is_not_an_entity_pivot() -> None:
    assert (
        _entities(
            {
                "source_id": "idx:access",
                "entities": [{"role": "action", "value": "999.999.999.999 *"}],
            },
            IDENTITY,
            {},
        )
        == []
    )


def test_entity_support_does_not_accept_a_substring_of_another_term() -> None:
    assert not _entity_supported(
        {"value": "script"},
        {"_raw": "bash: 196: Bad file descriptor", "host": "intranet_server"},
    )


def test_query_uses_field_equality_for_structured_identity() -> None:
    query = _query(
        "hb_kyoushi_s1",
        {"value": "33", "field": "uid", "terms": ()},
        '(source="/audit/audit.log")',
        anchor=1_616_534_612.0,
    )
    assert 'uid="33"' in query
    assert 'source="/audit/audit.log"' in query
    assert "TERM" not in query
    assert "_relate_delta=abs(_time" in query


def test_query_uses_term_for_address() -> None:
    query = _query("hb_kyoushi_s1", {"value": "172.16.100.151", "terms": ("172.16.100.151",)})
    assert 'TERM("172.16.100.151")' in query
    assert "_relate_delta=abs(_time" in query


def test_query_scopes_to_seed_source_and_sorts_toward_time() -> None:
    route = _route({"sources": ["/apache2/intranet.company.cyberrange.at-access.log.4"]})
    query = _query(
        "hb_kyoushi_s1",
        {"value": "172.16.100.151", "terms": ("172.16.100.151",)},
        route,
        anchor=1_616_533_976.0,
    )
    assert 'source="/apache2/intranet.company.cyberrange.at-access.log.4"' in query
    # sorted by time distance to the seed's own anchor, capped by the episode's needs
    assert "_relate_delta=abs(_time - 1616533976.000)" in query
    assert "sort limit=20 _relate_delta" in query


def test_route_falls_back_to_empty_without_sources() -> None:
    assert _route({"sources": []}) == ""
    assert _route({}) == ""


def _unit(
    kind: str,
    key: str,
    source: str,
    start: float,
    end: float,
    *,
    event_ids: tuple[str, ...] = (),
    notable_id: str = "",
    p_yes: float | None = None,
    share: float = 0.1,
) -> CaseUnit:
    value = key.split(":", 1)[1]
    return CaseUnit(
        f"{notable_id or kind}-{value}-{start}",
        kind,
        key,
        value,
        source,
        "h1",
        start,
        end,
        event_ids=event_ids,
        lines=({"line": "pivot line", "query": "search index=ix"},) if notable_id else (),
        notable_id=notable_id,
        measure=1.0,
        share=share,
        p_yes=p_yes,
    )


EVENTS = {
    name: {"host": "h1", "source": "/var/log/app.log", "time": START, "raw_sha256": name}
    for name in ("e1", "e2", "e3")
}


def test_a_single_signal_is_a_notable_not_a_case() -> None:
    signal = _unit("signal", "user:abe", "idx:auth", START, START + 60, notable_id="n1", p_yes=0.9)
    alone, _counters = _case_groups([signal])
    assert _case_from_members(alone[0], EVENTS, set()) is None

    episode = _unit("episode", "user:abe", "idx:audit", START + 30, START + 90, event_ids=("e1",))
    linked, _counters = _case_groups([signal, episode])
    case = _case_from_members(linked[0], EVENTS, set())
    assert case is not None
    assert len(case["sources"]) == 2
    assert len(case["evidence"]) >= 2


def test_an_entity_chain_censors_the_gap_and_the_day() -> None:
    near = _unit("episode", "address:10.0.0.1", "idx:a", START, START + 60)
    close = _unit("episode", "address:10.0.0.1", "idx:b", START + 2 * 3600, START + 7200 + 60)
    far = _unit("episode", "address:10.0.0.1", "idx:c", START + 40 * 3600, START + 40 * 3600 + 60)
    groups, counters = _case_groups([near, close, far])
    assert len(groups) == 2
    assert counters["gap"] == 1

    hourly = [
        _unit(
            "episode",
            "user:bob",
            "idx:a",
            START + index * 3 * 3600,
            START + index * 3 * 3600 + 60,
        )
        for index in range(10)
    ]
    _groups, windowed = _case_groups(hourly)
    assert windowed["window"] >= 1


def test_promotion_never_lifts_an_unjudged_row_into_a_judged_view() -> None:
    rows = [
        {"notable_id": f"n{index}", "generator": "deviation", "p_yes": 0.9} for index in range(60)
    ]
    rows[55] = {"notable_id": "n55", "generator": "deviation", "p_yes": None}
    cases = [{"case_id": "c1", "seed_notables": ["n0", "n55"], "related_notables": []}]

    judged, receipt = promote_case_members(rows, cases, [], judged_only=True)

    assert receipt["lifted"] == 0
    assert [row["notable_id"] for row in judged[:3]] == ["n0", "n1", "n2"]

    open_view, unjudged_receipt = promote_case_members(rows, cases, [], judged_only=False)

    assert unjudged_receipt["lifted"] == 1
    assert unjudged_receipt["ids"][0]["unjudged"] is True
    assert open_view[1]["notable_id"] == "n55"


def test_seed_records_rank_by_identity_not_file_order() -> None:
    identity = {"idx:access": {"fmt": "template", "actor_field": "v1", "objects": ["v2"]}}
    shares = {
        ("idx:access", "172.16.100.151"): 0.51,  # the attacker dominates its source
        ("idx:access", "172.16.0.9"): 0.01,  # a benign client is rare
    }
    spans = {("idx:access", "172.16.100.151"): (START, START + 9000)}
    rows: list[dict[str, Any]] = [
        {
            "notable_id": "benign-first",
            "generator": "peer_rare",
            "source_id": "idx:access",
            "first_seen": START + 100,
            "last_seen": START + 200,
            "entities": [{"role": "actor", "value": "172.16.0.9"}],
            "evidence": [{"earliest": START + 100, "latest": START + 200}],
        }
    ]
    rows += [
        {
            "notable_id": f"no-entity-{index}",
            "generator": "peer_rare",
            "source_id": "idx:access",
            "first_seen": START,
            "last_seen": START + 1,
            "entities": [{"role": "action", "value": "* * *"}],
        }
        for index in range(50)
    ]
    rows.append(
        {
            "notable_id": "attack-late",
            "generator": "similar_to_known",
            "source_id": "idx:access",
            "first_seen": START + 100,
            "last_seen": START + 200,
            "entities": [{"role": "actor", "value": "172.16.100.151"}],
            "evidence": [{"earliest": START + 100, "latest": START + 200}],
        }
    )
    seeds = _seed_records(rows, START, START + 9000, identity, shares, spans)
    seed_ids = [str(seed["id"]) for seed in seeds]
    # the attack notable sits beyond the old top-40 yet still becomes a seed, ranked first
    assert "attack-late" in seed_ids
    assert seed_ids.index("attack-late") < seed_ids.index("benign-first")


def test_relate_scopes_shared_sources_from_legacy_cards(tmp_path):
    import json

    from portal.modules.security.core.hunt.notables.relate import _identity_fields

    cards = [
        {"index": "ix", "sourcetype": name, "facts": {"sources": ["gacrux"]}}
        for name in ("mysql:status", "mysql:database")
    ]
    (tmp_path / "sources.json").write_text(json.dumps({"cards": cards}))
    info = _identity_fields(tmp_path)["ix:mysql:database"]
    assert _route(info) == 'sourcetype="mysql:database" (source="gacrux")'
