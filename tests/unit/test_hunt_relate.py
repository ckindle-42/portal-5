from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from portal.modules.security.core.hunt.notables.relate import RELATE_FILE, relate_stage

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
        if 'TERM("alice")' not in query and 'TERM("shell")' not in query:
            return []
        return [
            {
                "_time": START + 120,
                "_raw": "2023-11-14T22:15:20Z user=alice action=reverse_shell",
                "host": "web-1",
                "source": "/var/log/auth.log",
                "sourcetype": "auth",
                "_cd": "1:42",
            }
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
    assert receipt["requests"] == 4
    assert search.max_active > 1
    assert any('TERM("alice")' in query for query in search.queries)
    assert result["notables"][0]["measure"]["name"] == "relation_support"
    assert result["notables"][0]["evidence"][0]["event"]["event_id"] == "1:42"
    assert result["cases"][0]["evidence"][0]["source"] == "/var/log/auth.log"
    assert result["cases"][0]["links"][0]["shared_entities"] == ["alice", "shell"]
    assert len(result["cases"][0]["seed_notables"]) == 2


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
