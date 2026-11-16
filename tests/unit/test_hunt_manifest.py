from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from portal.modules.security.core.hunt.engine import _literal_term_segments
from portal.modules.security.core.hunt.executor import DEFAULT_BUDGETS, HuntBudget, HuntExecutor
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.knowledge import KnowledgeItem, load_for_run
from portal.modules.security.core.hunt.notables.manifest import (
    FamilySpec,
    _build_indexed,
    _provenance_query,
    audit_items,
    main,
    parse_source,
)


class _Embedder:
    model = "unit-embedding-model"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "execute" in text else [0.0, 1.0] for text in texts]

    def stats(self) -> dict[str, int]:
        return {"requests": 1}

    def close(self) -> None:
        pass


class _FakeSearch:
    """Answers by query substring; records every query it receives."""

    def __init__(self, answers: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.answers = answers or {}
        self.queries: list[tuple[str, float, float]] = []

    def iter_post(self, search: str, start: float, end: float) -> Any:
        self.queries.append((search, start, end))
        for marker, rows in self.answers.items():
            if marker in search:
                return iter(rows)
        return iter([])


def _card(index: str, sourcetype: str) -> SourceCard:
    return SourceCard(
        index=index,
        sourcetype=sourcetype,
        kind="activity",
        roles={"actor": ("user",), "action": ("action",), "object": ("path",)},
        understood=True,
        reason=None,
        fmt="json",
        coverage=1.0,
        fields=(),
        sample={},
        facts={},
        model={},
        cache_key="",
    )


def _cards_dir(tmp_path: Path, name: str, cards: list[SourceCard]) -> Path:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    payload = []
    for card in cards:
        stored = card.as_dict()
        stored["role_overrides"] = {
            "actor": {"field": "user", "mode": "literal"},
            "action": {"field": "action", "mode": "literal"},
            "objects": [{"field": "path", "mode": "literal"}],
            "overrides": [],
            "fields": {},
        }
        payload.append(stored)
    (directory / "sources.json").write_text(json.dumps({"cards": payload}))
    return directory


def _keyed_family(tmp_path: Path, name: str, index: str, user: str) -> tuple[str, _FakeSearch]:
    gather = tmp_path / name / "gather"
    logs = gather / "hostA" / "logs"
    logs.mkdir(parents=True)
    lines = [json.dumps({"user": user, "action": "execute", "path": "shell"})]
    lines.extend(
        json.dumps({"user": "goodperson", "action": "read", "path": "file"}) for _ in range(120)
    )
    (logs / "auth.log").write_text("\n".join(lines) + "\n")
    keys = tmp_path / name / "keys.jsonl"
    keys.write_text(
        json.dumps(
            {
                "digest": "d1",
                "host": "hostA",
                "source": "/auth.log",
                "line": 1,
                "labels": ["step_x"],
            }
        )
        + "\n"
    )
    cards = _cards_dir(tmp_path, f"{name}-cards", [_card(index, "auth.log")])
    spec = f"name={name},index={index},kind=keys,keys={keys},gather={gather},cards={cards}"
    search = _FakeSearch({f'"{user}"': [{"_raw": lines[0]}], '"goodperson"': [{"_raw": lines[1]}]})
    return spec, search


def test_build_audits_and_stores_keyed_families_with_lofo_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_a, search_a = _keyed_family(tmp_path, "fam_a", "idx_a", "alice")
    spec_b, search_b = _keyed_family(tmp_path, "fam_b", "idx_b", "bobby")
    answers = {**search_a.answers, **search_b.answers}
    search = _FakeSearch(answers)
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.manifest.embedding_from_env", _Embedder
    )
    manifest = tmp_path / "manifest.jsonl"
    store = tmp_path / "knowledge.duckdb"

    code = main(
        [
            "build",
            "--source",
            spec_a,
            "--source",
            spec_b,
            "--manifest",
            str(manifest),
            "--store",
            str(store),
        ],
        search=search,
    )

    assert code == 0
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert len(rows) == 4
    assert {(row["family"], row["label_kind"]) for row in rows} == {
        ("fam_a", "known_bad"),
        ("fam_a", "known_good"),
        ("fam_b", "known_bad"),
        ("fam_b", "known_good"),
    }
    bad = next(row for row in rows if row["label_kind"] == "known_bad")
    assert bad["statement"] == "actor alice did execute to shell"
    assert bad["label_basis"] == "attack_step"
    assert bad["query"].startswith('search index="idx_a" host="hostA" source="/auth.log"')
    out = capsys.readouterr().out
    assert "fam_a known_bad step_x: items=1 located=1" in out
    assert store.is_file()
    receipt = json.loads(store.with_suffix(".receipt.json").read_text())
    assert receipt["items"] == 4
    with load_for_run(store, run_index="idx_a") as loaded:
        families = {
            row[0]
            for row in loaded.connection.execute(
                "SELECT DISTINCT family FROM loaded_knowledge"
            ).fetchall()
        }
    assert families == {"fam_b"}


def test_audit_fails_loudly_when_an_item_locates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec, search = _keyed_family(tmp_path, "fam_a", "idx_a", "alice")
    search.answers.pop('"goodperson"')
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.manifest.embedding_from_env", _Embedder
    )
    manifest = tmp_path / "manifest.jsonl"
    store = tmp_path / "knowledge.duckdb"

    code = main(
        ["build", "--source", spec, "--manifest", str(manifest), "--store", str(store)],
        search=search,
    )

    assert code == 1
    err = capsys.readouterr().err
    assert "locate no events" in err
    assert "fam_a/unlabelled" in err
    assert manifest.is_file()
    assert not store.exists()


def test_proof_indexes_are_unreachable_on_the_build_path(tmp_path: Path) -> None:
    for index in ("wheeler", "hb_ait_wheeler", "cloudobs_aws", "hb_cloudobs_aws", "botsv1"):
        with pytest.raises(ValueError, match="proof index"):
            parse_source(f"name=proof,index={index},kind=keys,keys=k,gather=g,cards=c")
    search = _FakeSearch()
    code = main(
        [
            "build",
            "--source",
            "name=proof,index=wheeler,kind=keys,keys=k,gather=g,cards=c",
            "--manifest",
            str(tmp_path / "m.jsonl"),
            "--store",
            str(tmp_path / "s.duckdb"),
        ],
        search=search,
    )
    assert code == 1
    assert search.queries == []


def _indexed_answers(index: str, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "min(_time) as first": [
            {"sourcetype": "winlog", "count": 10, "first": 0.0, "last": 3600.0}
        ],
        "by sourcetype source": [{"sourcetype": "winlog", "source": "/win", "count": 10}],
        "by sourcetype host": [{"sourcetype": "winlog", "host": "h1", "count": 10}],
        "span=1d": [{"sourcetype": "winlog", "_time": 0.0, "count": 10}],
        f'search index="{index}"': rows,
        '"alice"': [{"_raw": "event"}],
    }


def test_labelled_family_builds_technique_items_from_the_carrying_field(tmp_path: Path) -> None:
    raw = json.dumps({"user": "alice", "action": "execute", "path": "shell"})
    rows = [{"_raw": raw, "host": "h1", "source": "/win", "p5_item": "T1059"}]
    search = _FakeSearch(_indexed_answers("corpus", rows))
    cards = _cards_dir(tmp_path, "corpus-cards", [_card("corpus", "winlog")])
    spec = FamilySpec(
        name="attack_data", index="corpus", kind="labelled", cards=cards, label_field="p5_item"
    )
    executor = HuntExecutor(search, HuntBudget(dict(DEFAULT_BUDGETS)))
    items, detail = _build_indexed(spec, executor, 0.0, 4000.0)

    assert len(items) == 1
    assert items[0].label == "T1059"
    assert items[0].label_kind == "known_bad"
    assert items[0].label_basis == "technique"
    assert items[0].statement == "actor alice did execute to shell"
    assert detail["events"] == 4  # one fake row per window; real events fall in one window
    assert detail["normalized"] == 4
    audit = audit_items(executor, items, 0.0, 4000.0)
    assert audit["items"] == 1


def test_knowledge_audit_reads_items_concurrently_and_keeps_report_order() -> None:
    class _AuditSearch:
        def __init__(self) -> None:
            self.lock = threading.Lock()
            self.active = 0
            self.peak = 0

        def iter_post_bounded(self, query: str, *_args: Any, **_kwargs: Any) -> Any:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.02)
            with self.lock:
                self.active -= 1
            yield {"query": query}

    search = _AuditSearch()
    executor = HuntExecutor(search, HuntBudget(dict(DEFAULT_BUDGETS)))
    items = [
        KnowledgeItem(
            statement=f"statement {index}",
            label=f"label {index:02}",
            label_kind="known_bad",
            label_basis="technique",
            family="family",
            split="build",
            index="idx",
            source_kind="activity",
            query=f"search index=idx id={index}",
        )
        for index in range(24)
    ]

    report = audit_items(executor, items, 0.0, 1.0)

    assert report["items"] == len(items)
    assert report["rows"] == len(items)
    assert search.peak == 8
    assert [row["label"] for row in report["counts"]] == [f"label {i:02}" for i in range(24)]


def test_window_family_builds_non_attack_day_known_good(tmp_path: Path) -> None:
    raw = json.dumps({"user": "alice", "action": "execute", "path": "shell"})
    rows = [{"_raw": raw, "host": "h1", "source": "/win"}]
    search = _FakeSearch(_indexed_answers("botsidx", rows))
    cards = _cards_dir(tmp_path, "bots-cards", [_card("botsidx", "winlog")])
    spec = FamilySpec(
        name="bots", index="botsidx", kind="window", cards=cards, good_window=(100.0, 200.0)
    )
    executor = HuntExecutor(search, HuntBudget(dict(DEFAULT_BUDGETS)))
    items, _detail = _build_indexed(spec, executor, 0.0, 4000.0)

    assert len(items) == 1
    assert items[0].label_kind == "known_good"
    assert items[0].label_basis == "non_attack_day"
    facts_queries = [query for query, _s, _e in search.queries if "by sourcetype" in query]
    assert facts_queries
    assert all(
        start == 100.0 and end == 200.0 for _q, start, end in search.queries if "tstats" in _q
    )


def test_audit_labels_reports_carriage_and_fails_on_unlocatable_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    search = _FakeSearch(
        {
            "by p5_item": [{"p5_item": "T1059", "count": 5}],
            'p5_item="T1059"': [{"_raw": "event"}],
        }
    )
    code = main(["audit-labels", "--index", "corpus", "--fields", "p5_item"], search=search)
    assert code == 0
    out = capsys.readouterr().out
    assert "p5_item: carriage=indexed distinct=1 located=1/1" in out

    broken = _FakeSearch({"by p5_item": [{"p5_item": "T1059", "count": 5}]})
    code = main(["audit-labels", "--index", "corpus", "--fields", "p5_item"], search=broken)
    assert code == 1


def test_source_spec_rejects_duplicate_indexes(tmp_path: Path) -> None:
    spec_a, _search_a = _keyed_family(tmp_path, "fam_a", "idx_a", "alice")
    duplicate = spec_a.replace("name=fam_a", "name=fam_b")
    code = main(
        [
            "build",
            "--source",
            spec_a,
            "--source",
            duplicate,
            "--manifest",
            str(tmp_path / "m.jsonl"),
            "--store",
            str(tmp_path / "s.duckdb"),
        ],
        search=_FakeSearch(),
    )
    assert code == 1


def test_provenance_query_uses_quoted_plain_terms_for_key_value_embedded_values() -> None:
    """Whole phrases stay quoted while too-short numeric fragments are omitted."""
    query = _provenance_query(
        "hb_kyoushi_s1", "intranet_server", "/audit/audit.log", ["type=CRED_ACQ uid=0"]
    )
    assert " TERM(" not in query
    assert '"type=CRED_ACQ"' in query
    assert '"uid=0"' in query
    assert query.startswith(
        'search index="hb_kyoushi_s1" host="intranet_server" source="/audit/audit.log"'
    )


def test_provenance_query_escapes_embedded_quotes() -> None:
    """Quoted boundaries split clean terms without emitting syntax fragments."""
    query = _provenance_query("foo", "h1", "/s", ['he said "yes"'])
    assert '"said"' in query
    assert '"yes"' not in query
    assert " TERM(" not in query


def test_provenance_query_numeric_value_is_quoted() -> None:
    """Numeric values under four characters do not become query terms."""
    query = _provenance_query("idx", "host", "/src", ["42", "admin"])
    assert '"admin"' in query
    assert '"42"' not in query
    assert " TERM(" not in query


def test_provenance_query_drops_star_adjacent_pieces() -> None:
    query = _provenance_query("idx", "host", "/src", ["alpha*medium*verylongsegment"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'


def test_default_segments_keep_dns_customer_domain_and_drop_star_neighbors() -> None:
    line = (
        "dnsmasq[14919]: reply 3x6-.1-.*SadBEXbCFTw*kitMRtD8ch5XbwBwIbmEHDcmi*"
        "/37v9m99Ips9CCbziwJcl-.customers_2020.xlsx.kiirjekuimkpcrcioastvkeodpnimx.biz "
        "is 10.195.165.2"
    )

    terms = _literal_term_segments(line)
    query = _provenance_query("santos", "hostA", "/dnsmasq.log", [line])

    assert len(terms) <= 2
    assert any(
        term == "customers_2020.xlsx.kiirjekuimkpcrcioastvkeodpnimx.biz"
        or term in {"customers", "2020", "xlsx", "kiirjekuimkpcrcioastvkeodpnimx", "biz"}
        for term in terms
    )
    assert all("*" not in term for term in terms)
    assert "SadBEXbCFTw" not in terms
    assert "kitMRtD8ch5XbwBwIbmEHDcmi" not in terms
    assert any(f'"{term}"' in query for term in terms)
    assert "kitMRtD8ch5XbwBwIbmEHDcmi" not in query


def test_default_segments_keep_key_value_phrases_and_drop_unclean_values() -> None:
    terms = _literal_term_segments("type=CRED_ACQ uid=0")

    assert terms == ("type=CRED_ACQ", "uid=0")
    assert all(len(term) >= 4 for term in terms)
    assert _literal_term_segments("foo^bar") == ()
    assert _literal_term_segments("alpha?beta") == ()


def test_provenance_query_drops_wildcard_value_without_long_segments() -> None:
    query = _provenance_query("idx", "host", "/src", ["***"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'


def test_provenance_query_drops_values_shorter_than_four_characters() -> None:
    query = _provenance_query("idx", "host", "/src", ["bob"])

    assert query == 'search index="idx" host="host" source="/src" | head 5'
