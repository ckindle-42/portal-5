from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from portal.modules.security.core.hunt.notables.relate import (
    MAX_EVENTS_PER_QUERY,
    RELATE_FILE,
    _case_groups,
    _cases,
    _entities,
    _entity_supported,
    _episode_window,
    _identity_fields,
    _identity_role,
    _load_metrics,
    _query,
    _route,
    _seed_records,
    _share_weight,
    relate_stage,
)

START = 1_700_000_000.0

# A source whose actor is a client IP (web phase), a program-actor source (auth), and a
# key=value source whose actor is a uid (audit). These mirror the two corpora's cards.
IDENTITY = {
    "idx:access": {"fmt": "template", "actor_field": "v1", "objects": ["v2"]},
    "idx:auth": {"fmt": "template", "actor_field": "program", "objects": ["v1", "v2"]},
    "idx:audit": {"fmt": "kv", "actor_field": "uid", "objects": []},
}


def _metrics_store(tmp_path: Path) -> Path:
    import duckdb

    store = tmp_path / "behaviours.duckdb"
    con = duckdb.connect(str(store))
    con.execute(
        "CREATE TABLE behaviours (source_id VARCHAR, actor VARCHAR, action VARCHAR, "
        "object VARCHAR, events BIGINT, first_seen DOUBLE, last_seen DOUBLE)"
    )
    rows = [
        # the attacker dominates the access source (1311 of 2575 events)
        (
            "idx:access",
            "172.16.100.151",
            "* - - * * * * * *",
            "* GET / HTTP/1.1 200",
            1311,
            START + 100,
            START + 5000,
        ),
        (
            "idx:access",
            "172.16.0.98",
            "* - - * * * * * *",
            "* GET / HTTP/1.1 200",
            392,
            START + 100,
            START + 3000,
        ),
        (
            "idx:access",
            "::1",
            "* - - * * * * * *",
            "* OPTIONS * HTTP/1.0 200",
            281,
            START + 100,
            START + 4000,
        ),
        # the benign root dominates the audit source; the attack users are rare
        ("idx:audit", "0", "USER_AUTH", "", 13296, START + 100, START + 9000),
        ("idx:audit", "33", "USER_AUTH", "", 4, START + 4000, START + 4100),
        ("idx:audit", "1001", "USER_CMD", "", 2, START + 4050, START + 4120),
        # auth: the program is the actor; the user is in the object slot
        (
            "idx:auth",
            "CRON",
            "pam_unix(cron:session): session opened",
            "root",
            3153,
            START + 100,
            START + 9000,
        ),
        (
            "idx:auth",
            "sudo",
            "pam_unix(sudo:session): session opened",
            "root",
            6,
            START + 4000,
            START + 4100,
        ),
    ]
    con.executemany("INSERT INTO behaviours VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute(
        "CREATE TABLE source_stats AS SELECT source_id, SUM(events) AS events "
        "FROM behaviours GROUP BY source_id"
    )
    con.close()
    return store


def _run_dir(tmp_path: Path, *, store: bool = True) -> Path:
    out = tmp_path / "kyoushi"
    out.mkdir()
    (out / "sources.json").write_text(
        json.dumps(
            {
                "index": "hb_kyoushi_s1",
                "start": START,
                "end": START + 9000,
                "cards": [
                    {
                        "index": "hb_kyoushi_s1",
                        "sourcetype": "access",
                        "source_id": "idx:access",
                        "structure": "template",
                        "role_overrides": {
                            "actor": {"field": "v1", "mode": "literal"},
                            "objects": [{"field": "v2", "mode": "shape"}],
                        },
                        "facts": {
                            "sources": ["/apache2/intranet.company.cyberrange.at-access.log.4"]
                        },
                    },
                    {
                        "index": "hb_kyoushi_s1",
                        "sourcetype": "audit",
                        "source_id": "idx:audit",
                        "structure": "kv",
                        "role_overrides": {
                            "actor": {"field": "uid", "mode": "literal"},
                            "objects": [],
                        },
                        "facts": {"sources": ["/audit/audit.log"]},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    if store:
        _metrics_store(tmp_path)
    notable = {
        "notable_id": "seed-1",
        "generator": "similar_to_known",
        "source_id": "idx:access",
        "p_yes": 0.91,
        "first_seen": START + 200,
        "last_seen": START + 300,
        "entities": [
            {"role": "actor", "value": "172.16.100.151"},
            {
                "role": "action",
                "value": "172.16.100.151 - - * * * HTTP/1.1 200 * - python-requests/2.25.1",
            },
        ],
        "evidence": [
            {
                "line": "172.16.100.151 - - [23/Mar/2021:21:12:56 +0000] GET /",
                "query": 'search index="hb_kyoushi_s1" TERM("172.16.100.151")',
                "earliest": START + 200,
                "latest": START + 300,
            }
        ],
    }
    audit_seed = {
        "notable_id": "seed-2",
        "generator": "similar_to_known",
        "source_id": "idx:audit",
        "p_yes": 0.80,
        "first_seen": START + 4000,
        "last_seen": START + 4100,
        "entities": [
            {"role": "actor", "value": "33"},
            {"role": "action", "value": "USER_AUTH"},
        ],
        "evidence": [
            {
                "line": "type=USER_AUTH uid=33 acct=msperl exe=/bin/su",
                "query": 'search index="hb_kyoushi_s1" TERM("USER_AUTH")',
                "earliest": START + 4000,
                "latest": START + 4100,
            }
        ],
    }
    (out / "notables.jsonl").write_text(
        json.dumps(notable) + "\n" + json.dumps(audit_seed) + "\n", encoding="utf-8"
    )
    return out


class _Search:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.queries: list[str] = []

    def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.queries.append(query)
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        if "172.16.100.151" in query:
            return [
                {
                    "_time": START + 250,
                    "_raw": '172.16.100.151 - - [23/Mar/2021:21:12:56 +0000] "GET / HTTP/1.1" 200',
                    "host": "web-1",
                    "source": "/var/log/access.log",
                    "sourcetype": "access",
                    "_cd": "1:42",
                },
                {"_raw": "missing event identity fields"},
            ]
        if 'uid="33"' in query:
            return [
                {
                    "_time": START + 4005,
                    "_raw": "type=USER_AUTH msg=audit(...): uid=33 acct=msperl exe=/bin/su",
                    "host": "web-1",
                    "source": "/var/log/audit.log",
                    "sourcetype": "audit",
                    "_cd": "1:43",
                }
            ]
        return []


# --- identity model ---


def test_identity_role_is_object_for_program_actor_sources() -> None:
    assert _identity_role({"actor_field": "program"}) == "object"
    assert _identity_role({"actor_field": "uid"}) == "actor"
    assert _identity_role({"actor_field": ""}) == "object"


def test_identity_fields_reads_role_overrides_from_cards(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)
    info = _identity_fields(out)
    assert info["idx:access"]["actor_field"] == "v1"
    assert info["idx:audit"]["actor_field"] == "uid"
    assert info["idx:audit"]["fmt"] == "kv"
    assert info["idx:access"]["sources"] == ["/apache2/intranet.company.cyberrange.at-access.log.4"]


# --- pivot entity selection ---


def test_entities_extract_address_and_identity_value(tmp_path: Path) -> None:
    _metrics_store(tmp_path)
    shares, _ = _load_metrics(tmp_path / "behaviours.duckdb")
    entities = _entities(
        {
            "source_id": "idx:access",
            "entities": [
                {"role": "actor", "value": "172.16.100.151"},
                {"role": "action", "value": "172.16.100.151 - - * * * HTTP/1.1 200"},
            ],
        },
        IDENTITY,
        shares,
    )
    addresses = [entity for entity in entities if entity["role"] == "address"]
    assert [entity["value"] for entity in addresses] == ["172.16.100.151"]
    assert addresses[0]["case_anchor"] is True
    # the attacker dominates its source, so its within-source share is the weight
    assert addresses[0]["weight"] == _share_weight("idx:access", "172.16.100.151", shares)
    assert addresses[0]["weight"] > 0.5


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


# --- metrics ---


def test_load_metrics_share_and_span(tmp_path: Path) -> None:
    store = _metrics_store(tmp_path)
    shares, spans = _load_metrics(store)
    assert shares[("idx:access", "172.16.100.151")] > 0.5  # dominates
    assert spans[("idx:access", "172.16.100.151")] == (START + 100, START + 5000)
    # the attack user is rare in its source, so its share is small
    assert shares[("idx:audit", "33")] < 0.01


def test_load_metrics_empty_without_store(tmp_path: Path) -> None:
    shares, spans = _load_metrics(tmp_path / "missing.duckdb")
    assert shares == {}
    assert spans == {}


# --- episode window ---


def test_episode_window_grows_to_identity_activity_span(tmp_path: Path) -> None:
    store = _metrics_store(tmp_path)
    _shares, spans = _load_metrics(store)
    entities = [{"role": "address", "value": "172.16.100.151"}]
    low, high = _episode_window(
        {"first_seen": START + 200, "last_seen": START + 300, "evidence": []},
        "idx:access",
        START,
        START + 9000,
        spans,
        entities,
    )
    # the window is the identity's measured activity span, not ±1 h around the seed
    assert (low, high) == (START + 100, START + 5000)


# --- query ---


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


# --- case grouping ---


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


# --- stage ---


def test_relate_pivots_identity_not_program_names(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)
    search = _Search()

    receipt = relate_stage(out=out, search=search)

    result = json.loads((out / RELATE_FILE).read_text(encoding="utf-8"))
    assert any('TERM("172.16.100.151")' in query for query in search.queries)
    assert any('uid="33"' in query for query in search.queries)
    # every pivot is scoped to its seed's source and sorted toward the seed's time
    assert any(
        'source="/apache2/intranet.company.cyberrange.at-access.log.4"' in query
        for query in search.queries
    )
    assert any('source="/audit/audit.log"' in query for query in search.queries)
    assert all("_relate_delta=abs(_time" in query for query in search.queries)
    # no program-name or action-token pivots (USER_AUTH, systemd-logind)
    assert not any("USER_AUTH" in query for query in search.queries)
    assert result["notables"][0]["measure"]["name"] == "relation_support"
    assert result["notables"][0]["basis"] == "identity_episode"
    assert result["notables"][0]["evidence"][0]["event"]["event_id"] == "1:42"
    assert receipt["coverage_complete"] is False
    assert sum(item["unreferenced_events"] for item in receipt["coverage"]) == 1


def test_relate_capped_query_is_still_complete_coverage(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)

    class _CappedSearch:
        def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
            if "172.16.100.151" in query:
                return [
                    {
                        "_time": START + 250,
                        "_raw": (
                            f'172.16.100.151 - - [23/Mar/2021:21:12:56 +0000] "GET /{index} '
                            'HTTP/1.1" 200'
                        ),
                        "host": "web-1",
                        "source": "/var/log/access.log",
                        "sourcetype": "access",
                        "_cd": f"1:{index}",
                    }
                    for index in range(MAX_EVENTS_PER_QUERY)
                ]
            if 'uid="33"' in query:
                return [
                    {
                        "_time": START + 4005,
                        "_raw": "type=USER_AUTH msg=audit(...): uid=33 acct=msperl exe=/bin/su",
                        "host": "web-1",
                        "source": "/var/log/audit.log",
                        "sourcetype": "audit",
                        "_cd": "1:43",
                    }
                ]
            return []

    receipt = relate_stage(out=out, search=_CappedSearch())

    # the 20-row result is the deliberate per-query effort budget, not a coverage gap
    assert receipt["coverage_complete"] is True
    assert receipt["capped_queries"] == 1


def test_relate_rejects_nontraining_indexes_before_reading(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)
    sources = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    sources["index"] = "botsv1"
    (out / "sources.json").write_text(json.dumps(sources), encoding="utf-8")
    search = _Search()

    try:
        relate_stage(out=out, search=search)
    except ValueError as error:
        assert "training indexes" in str(error)
    else:
        raise AssertionError("the relate runner accepted a proof index")
    assert search.queries == []


def test_product_relate_uses_judged_notables_only(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)
    rows = (out / "notables.jsonl").read_text(encoding="utf-8").splitlines()
    unjudged = json.loads(rows[1])
    unjudged["p_yes"] = None
    (out / "notables.jsonl").write_text(
        rows[0] + "\n" + json.dumps(unjudged) + "\n", encoding="utf-8"
    )

    receipt = relate_stage(out=out, search=_Search(), judged_only=True)

    assert receipt["seeds"] == 1
    assert receipt["unjudged_skipped"] == 1


def test_cases_order_by_best_seed_then_relation_distinctiveness() -> None:
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
        "10.0.0.3",
        "10.0.0.2",
        "10.0.0.1",
    ]


def test_query_results_without_exact_entity_support_are_discarded(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)

    class _BroadSearch:
        def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
            return [
                {
                    "_time": START + 250,
                    "_raw": "unrelated event with no seed entity",
                    "host": "web-1",
                    "source": "/var/log/access.log",
                    "sourcetype": "access",
                    "_cd": "1:43",
                }
            ]

    receipt = relate_stage(out=out, search=_BroadSearch())

    result = json.loads((out / RELATE_FILE).read_text(encoding="utf-8"))
    assert receipt["related_events"] == 0
    assert result["notables"] == []
    assert result["cases"] == []
