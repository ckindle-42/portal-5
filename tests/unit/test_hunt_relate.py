from __future__ import annotations

from typing import Any

from portal.modules.security.core.hunt.notables.relate import (
    _case_groups,
    _case_order,
    _cases,
    _entities,
    _entity_supported,
    _identity_role,
    _query,
    _route,
    _seed_records,
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


def test_case_groups_link_by_shared_address_and_user_chain() -> None:
    seeds = [
        {
            "id": "attack-a",
            "source_id": "idx:access",
            "start": START,
            "end": START + 600,
            "entities": [
                {
                    "role": "address",
                    "value": "172.16.100.151",
                    "case_anchor": True,
                    "kind": "address",
                }
            ],
        },
        {
            "id": "attack-b",
            "source_id": "idx:access",
            "start": START + 300,
            "end": START + 900,
            "entities": [
                {
                    "role": "address",
                    "value": "172.16.100.151",
                    "case_anchor": True,
                    "kind": "address",
                }
            ],
        },
        {
            "id": "noise",
            "source_id": "idx:access",
            "start": START + 300,
            "end": START + 900,
            "entities": [{"role": "actor", "value": "systemd-logind"}],
        },
    ]
    assert _case_groups(seeds) == [["attack-a", "attack-b"]]


def test_case_groups_chain_users_in_the_same_source() -> None:
    seeds = [
        {
            "id": "www-data",
            "source_id": "idx:audit",
            "start": START + 4000,
            "end": START + 4100,
            "entities": [{"role": "actor", "value": "33", "case_anchor": True, "kind": "user"}],
        },
        {
            "id": "msperl",
            "source_id": "idx:audit",
            "start": START + 4050,
            "end": START + 4120,
            "entities": [{"role": "actor", "value": "1001", "case_anchor": True, "kind": "user"}],
        },
    ]
    assert _case_groups(seeds) == [["msperl", "www-data"]]


def test_cases_keep_only_evidence_linked_to_an_episode_seed() -> None:
    seeds = [
        {
            "id": "attack-a",
            "source_id": "idx:access",
            "start": START,
            "end": START + 600,
            "entities": [
                {
                    "role": "address",
                    "value": "172.16.100.151",
                    "case_anchor": True,
                    "kind": "address",
                }
            ],
        },
        {
            "id": "attack-b",
            "source_id": "idx:access",
            "start": START + 300,
            "end": START + 900,
            "entities": [
                {
                    "role": "address",
                    "value": "172.16.100.151",
                    "case_anchor": True,
                    "kind": "address",
                }
            ],
        },
    ]
    event = {"time": START + 400, "host": "web-1", "source": "/var/log/access.log"}
    related = [
        {
            "notable_id": "attack-event",
            "relation_score": 1.0,
            "relations": [{"seed_id": "attack-a", "shared_entities": ["172.16.100.151"]}],
            "evidence": [{"event": event}],
        },
        {
            "notable_id": "unrelated-seed-event",
            "relation_score": 0.5,
            "relations": [{"seed_id": "some-other-seed", "shared_entities": ["10.0.0.9"]}],
            "evidence": [{"event": {**event, "time": START + 500}}],
        },
    ]

    cases = _cases(seeds, related)

    assert len(cases) == 1
    assert cases[0]["anchor_entity"] == "172.16.100.151"
    assert cases[0]["related_notables"] == ["attack-event"]


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


def test_cases_order_by_independent_seed_agreement_before_seed_rank_and_size() -> None:
    seeds = []
    related = []
    for seed_id, rank, address, share, generator in (
        ("benign-a", 0, "10.0.0.1", 0.9, "similar_to_known"),
        ("benign-b", 1, "10.0.0.1", 0.9, "similar_to_known"),
        ("attack-a", 10, "10.0.0.2", 0.1, "similar_to_known"),
        ("attack-b", 11, "10.0.0.2", 0.1, "similar_to_known"),
    ):
        seeds.append(
            {
                "id": seed_id,
                "source_id": "idx:access",
                "start": START,
                "end": START + 5000,
                "entities": [
                    {
                        "value": address,
                        "case_anchor": True,
                        "kind": "address",
                        "weight": share,
                    }
                ],
                "rank": rank,
                "original_rank": rank,
                "row": {"generator": generator},
            }
        )
    for index in range(4):
        related.append(
            {
                "notable_id": f"benign-event-{index}",
                "relation_score": 10.0,
                "relations": [
                    {"seed_id": "benign-a" if index % 2 == 0 else "benign-b", "seed_rank": index}
                ],
                "evidence": [
                    {
                        "event": {
                            "time": START + 1000 * (index + 1),
                            "host": "web-1",
                            "source": "/access.log",
                        }
                    }
                ],
            }
        )
    for index, moment in enumerate((START + 100, START + 110)):
        related.append(
            {
                "notable_id": f"attack-event-{index}",
                "relation_score": 0.1,
                "relations": [
                    {"seed_id": "attack-a", "seed_rank": 10},
                    {"seed_id": "attack-b", "seed_rank": 11},
                ],
                "evidence": [{"event": {"time": moment, "host": "web-1", "source": "/access.log"}}],
            }
        )

    cases = _cases(seeds, related)

    assert [case["anchor_entity"] for case in cases[:2]] == ["10.0.0.2", "10.0.0.1"]


def test_cases_order_by_independent_generators_when_seed_support_ties() -> None:
    seeds = []
    related = []
    for prefix, address, generators in (
        ("independent", "10.0.0.1", ("alerts", "similar_to_known")),
        ("same-generator", "10.0.0.2", ("similar_to_known", "similar_to_known")),
    ):
        for suffix, generator in zip(("a", "b"), generators, strict=True):
            seeds.append(
                {
                    "id": f"{prefix}-{suffix}",
                    "source_id": "idx:access",
                    "start": START,
                    "end": START + 5000,
                    "entities": [
                        {"value": address, "case_anchor": True, "kind": "address", "weight": 0.1}
                    ],
                    "rank": 5 + int(suffix == "b"),
                    "original_rank": 5 + int(suffix == "b"),
                    "row": {"generator": generator},
                }
            )
        related.append(
            {
                "notable_id": f"event-{prefix}",
                "relation_score": 10.0 if prefix == "same-generator" else 0.1,
                "relations": [
                    {"seed_id": f"{prefix}-a", "seed_rank": 5},
                    {"seed_id": f"{prefix}-b", "seed_rank": 6},
                ],
                "evidence": [
                    {"event": {"time": START + 100, "host": "web-1", "source": "/access.log"}}
                ],
            }
        )

    cases = _cases(seeds, related)

    assert [case["anchor_entity"] for case in cases] == ["10.0.0.1", "10.0.0.2"]


def test_case_order_prefers_distinctive_identities_then_shorter_span() -> None:
    distinctive = {"case_id": "distinctive", "start": START, "end": START + 100, "score": 0.1}
    common = {"case_id": "common", "start": START, "end": START + 10, "score": 10.0}
    assert _case_order(distinctive, 1, 1, 0.1) < _case_order(common, 1, 1, 0.9)

    short = {"case_id": "short", "start": START, "end": START + 10, "score": 0.1}
    long = {"case_id": "long", "start": START, "end": START + 100, "score": 10.0}
    assert _case_order(short, 1, 1, 0.5) < _case_order(long, 1, 1, 0.5)


def test_cases_use_relation_score_after_ordering_features_tie() -> None:
    seeds = []
    related = []
    for prefix, rank, score, address in (
        ("later", 4, 10.0, "10.0.0.1"),
        ("seed-tie-low", 2, 0.5, "10.0.0.2"),
        ("seed-tie-high", 2, 2.0, "10.0.0.3"),
    ):
        ids = [f"{prefix}-a", f"{prefix}-b"]
        for seed_id, seed_rank in zip(ids, (rank, rank + 1), strict=True):
            seeds.append(
                {
                    "id": seed_id,
                    "source_id": f"idx:{prefix}",
                    "start": START,
                    "end": START + 600,
                    "entities": [
                        {
                            "role": "address",
                            "value": address,
                            "case_anchor": True,
                            "kind": "address",
                        }
                    ],
                    "rank": seed_rank,
                    "original_rank": seed_rank,
                }
            )
        related.append(
            {
                "notable_id": f"event-{prefix}",
                "relation_score": score,
                "relations": [{"seed_id": ids[0], "seed_rank": rank}],
                "evidence": [
                    {
                        "event": {
                            "time": START + rank,
                            "host": "web-1",
                            "source": f"/{prefix}.log",
                        }
                    }
                ],
            }
        )

    cases = _cases(seeds, related)

    assert [case["anchor_entity"] for case in cases] == [
        "10.0.0.1",
        "10.0.0.3",
        "10.0.0.2",
    ]


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
