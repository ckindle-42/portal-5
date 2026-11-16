from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from portal.modules.security.core.hunt.notables.relate import (
    RELATE_FILE,
    _case_groups,
    _cases,
    _entities,
    _entity_supported,
    relate_stage,
)

START = 1_700_000_000.0


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
        if all(
            term not in query for term in ('TERM("alice")', 'TERM("shell")', 'TERM("192.0.2.10")')
        ):
            return []
        return [
            {
                "_time": START + 120,
                "_raw": "2023-11-14T22:15:20Z user=alice action=reverse_shell peer=192.0.2.10",
                "host": "web-1",
                "source": "/var/log/auth.log",
                "sourcetype": "auth",
                "_cd": "1:42",
            },
            {"_raw": "missing event identity fields"},
        ]


def _run_dir(tmp_path: Path) -> Path:
    out = tmp_path / "kyoushi"
    out.mkdir()
    (out / "sources.json").write_text(
        json.dumps({"index": "hb_kyoushi_s1", "start": START, "end": START + 3600}),
        encoding="utf-8",
    )
    notable = {
        "notable_id": "seed-1",
        "generator": "similar_to_known",
        "source_id": "hb_kyoushi_s1:auth",
        "p_yes": 0.91,
        "first_seen": START + 100,
        "last_seen": START + 110,
        "entities": [
            {"role": "actor", "value": "alice"},
            {"role": "object", "value": "shell"},
            {"role": "action", "value": "192.0.2.10 - - * * * HTTP/1.1"},
        ],
        "evidence": [
            {
                "line": "user=alice action=login",
                "query": 'search index="hb_kyoushi_s1" TERM("alice")',
                "earliest": START + 100,
                "latest": START + 110,
            }
        ],
    }
    neighbour = {
        **notable,
        "notable_id": "seed-2",
        "p_yes": 0.80,
        "entities": [
            {"role": "actor", "value": "alice"},
            {"role": "object", "value": "connection"},
            {"role": "action", "value": "192.0.2.10 - - * * * HTTP/1.1"},
        ],
    }
    (out / "notables.jsonl").write_text(
        json.dumps(notable) + "\n" + json.dumps(neighbour) + "\n", encoding="utf-8"
    )
    return out


def test_relate_reads_top_entities_concurrently_and_writes_case_evidence(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)
    search = _Search()

    receipt = relate_stage(out=out, search=search)

    result = json.loads((out / RELATE_FILE).read_text(encoding="utf-8"))
    assert receipt["requests"] == 6
    assert search.max_active > 1
    assert any('TERM("alice")' in query for query in search.queries)
    assert result["notables"][0]["measure"]["name"] == "relation_support"
    assert result["notables"][0]["evidence"][0]["event"]["event_id"] == "1:42"
    assert result["cases"][0]["evidence"][0]["source"] == "/var/log/auth.log"
    assert result["cases"][0]["anchor_entity"] == "192.0.2.10"
    assert "192.0.2.10" in result["cases"][0]["links"][0]["shared_entities"]
    assert len(result["cases"][0]["seed_notables"]) == 2
    assert receipt["coverage_complete"] is False
    assert sum(item["unreferenced_events"] for item in receipt["coverage"]) == 5


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


def test_entity_pivots_use_exact_values_and_extract_actor_address() -> None:
    entities = _entities(
        {
            "entities": [
                {
                    "role": "action",
                    "value": "172.16.100.151 - - * * * HTTP/1.1 200 * - python-requests/2.25.1",
                },
                {"role": "object", "value": "* /shell.php"},
            ]
        }
    )

    assert entities == [
        {
            "role": "actor_address",
            "value": "172.16.100.151",
            "terms": ("172.16.100.151",),
            "case_anchor": True,
        }
    ]


def test_entity_support_does_not_accept_a_substring_of_another_term() -> None:
    assert not _entity_supported(
        {"value": "script"},
        {"_raw": "bash: 196: Bad file descriptor", "host": "intranet_server"},
    )


def test_invalid_ipv4_text_is_not_an_entity_pivot() -> None:
    assert _entities({"entities": [{"role": "action", "value": "999.999.999.999 *"}]}) == []


def test_case_groups_require_a_shared_address_not_a_wildcard_or_service_actor() -> None:
    seeds = [
        {
            "id": "attack-a",
            "start": START,
            "end": START + 600,
            "entities": [{"role": "actor_address", "value": "172.16.100.151", "case_anchor": True}],
        },
        {
            "id": "attack-b",
            "start": START + 300,
            "end": START + 900,
            "entities": [{"role": "actor_address", "value": "172.16.100.151", "case_anchor": True}],
        },
        {
            "id": "noise",
            "start": START + 300,
            "end": START + 900,
            "entities": [
                {"role": "actor", "value": "systemd-logind"},
                {"role": "object", "value": "*"},
            ],
        },
    ]

    assert _case_groups(seeds) == [("172.16.100.151", ["attack-a", "attack-b"])]


def test_cases_keep_only_evidence_linked_to_the_shared_address() -> None:
    seeds = [
        {
            "id": "attack-a",
            "start": START,
            "end": START + 600,
            "entities": [{"role": "actor_address", "value": "172.16.100.151", "case_anchor": True}],
        },
        {
            "id": "attack-b",
            "start": START + 300,
            "end": START + 900,
            "entities": [{"role": "actor_address", "value": "172.16.100.151", "case_anchor": True}],
        },
    ]
    event = {"time": START + 400, "host": "web-1", "source": "/auth.log"}
    related = [
        {
            "notable_id": "attack-event",
            "relation_score": 1.0,
            "relations": [{"seed_id": "attack-a", "shared_entities": ["172.16.100.151"]}],
            "evidence": [{"event": event}],
        },
        {
            "notable_id": "cooccurrence-noise",
            "relation_score": 0.5,
            "relations": [{"seed_id": "attack-a", "shared_entities": ["script"]}],
            "evidence": [{"event": {**event, "time": START + 500}}],
        },
    ]

    cases = _cases(seeds, related)

    assert len(cases) == 1
    assert cases[0]["anchor_entity"] == "172.16.100.151"
    assert cases[0]["related_notables"] == ["attack-event"]


def test_query_results_without_exact_entity_support_are_discarded(tmp_path: Path) -> None:
    out = _run_dir(tmp_path)

    class _BroadSearch:
        def iter_post(self, query: str, start: float, end: float) -> list[dict[str, Any]]:
            return [
                {
                    "_time": START + 120,
                    "_raw": "unrelated event with no seed entity",
                    "host": "web-1",
                    "source": "/var/log/auth.log",
                    "sourcetype": "auth",
                    "_cd": "1:43",
                }
            ]

    receipt = relate_stage(out=out, search=_BroadSearch())

    result = json.loads((out / RELATE_FILE).read_text(encoding="utf-8"))
    assert receipt["related_events"] == 0
    assert result["notables"] == []
    assert result["cases"] == []
