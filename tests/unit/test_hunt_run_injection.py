from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from portal.modules.security.core.hunt.executor import HuntBudgetExceededError
from portal.modules.security.core.hunt.notables.__main__ import main
from portal.modules.security.core.hunt.notables.behaviours import (
    _INSERT,
    ExampleEvent,
    aggregate_events,
    create_events,
    identity_plan,
    keyed_rows,
)
from portal.modules.security.core.hunt.notables.cards import SourceCard
from portal.modules.security.core.hunt.notables.knowledge import (
    KnowledgeError,
    KnowledgeItem,
    build_store,
)
from portal.modules.security.core.hunt.notables.run import configure_ledger
from portal.modules.security.core.hunt.notables.sample import SourceFacts


class _Embedder:
    model = "unit-embedding-model"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "execute" in text else [0.0, 1.0] for text in texts]

    def stats(self) -> dict[str, int]:
        return {"requests": 1}

    def close(self) -> None:
        pass


class _RecordingSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def iter_post(self, search: str, start: float, end: float) -> Any:
        self.queries.append(search)
        return iter([])


def test_ledger_records_capped_read_and_extracted_values(tmp_path: Path) -> None:
    class _Rows:
        def iter_post(self, _search: str, _start: float, _end: float) -> Any:
            return iter(
                [
                    {"_raw": "first value", "actor": "alice"},
                    {"_raw": "second value", "actor": "bob"},
                ]
            )

    executor = configure_ledger(_Rows(), tmp_path, "behaviours")
    read = executor.read(
        'search index="runidx" sourcetype="activity" | head 1',
        10.0,
        20.0,
        kind="discovery",
        row_cap=1,
        source_id="runidx:activity",
    )

    row = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert read.reason == "row_cap"
    assert row == {
        "stage": "behaviours",
        "source_id": "runidx:activity",
        "part": None,
        "query": 'search index="runidx" sourcetype="activity" | head 1',
        "window_start": 10.0,
        "window_end": 20.0,
        "rows": 1,
        "capped": True,
        "reason": "row_cap",
        "values_extracted": ["first value", "alice"],
    }


def test_ledger_records_a_read_that_exhausts_the_event_budget(tmp_path: Path) -> None:
    class _Rows:
        def iter_post(self, _search: str, _start: float, _end: float) -> Any:
            return iter([{"_raw": "one"}, {"_raw": "two"}])

    executor = configure_ledger(_Rows(), tmp_path, "behaviours")

    def exhaust(_spend: str, _count: int) -> None:
        raise HuntBudgetExceededError("event_budget_exhausted")

    executor.budget.record_rows = exhaust  # type: ignore[method-assign]

    with pytest.raises(HuntBudgetExceededError):
        executor.read("search index=runidx", 10.0, 20.0, kind="discovery")

    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows[0]["rows"] == 2
    assert rows[0]["values_extracted"] == ["one", "two"]


def test_ledger_records_partial_rows_before_a_search_budget_error(tmp_path: Path) -> None:
    class _Rows:
        def iter_post(self, _search: str, _start: float, _end: float) -> Any:
            yield {"_raw": "partial row"}
            raise HuntBudgetExceededError("event_budget_exhausted")

    executor = configure_ledger(_Rows(), tmp_path, "behaviours")

    with pytest.raises(HuntBudgetExceededError):
        executor.read("search index=runidx", 10.0, 20.0, kind="discovery")

    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows[0]["rows"] == 1
    assert rows[0]["capped"] is False
    assert rows[0]["reason"] == "censored"
    assert rows[0]["values_extracted"] == ["partial row"]


def _run_card() -> SourceCard:
    return SourceCard(
        index="runidx",
        sourcetype="activity",
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


def _run_out(tmp_path: Path) -> Path:
    """A cards+behaviours output built through the real keying and aggregation path."""
    out = tmp_path / "run"
    out.mkdir()
    card = _run_card()
    (out / "sources.json").write_text(json.dumps({"cards": [card.as_dict()]}))
    raw = json.dumps({"user": "alice", "action": "execute", "path": "shell"})
    fields = {"user": "alice", "action": "execute", "path": "shell"}
    events = [
        ExampleEvent("runidx:activity", "h1", 10.0, raw, fields, 0.0, 60.0),
        ExampleEvent("runidx:activity", "h1", 20.0, raw, fields, 0.0, 60.0),
    ]
    facts = SourceFacts(
        index="runidx",
        sourcetype="activity",
        events=2,
        first=0.0,
        last=60.0,
        hosts=("h1",),
        host_count=1,
        sources=("/act",),
        source_count=1,
    )
    plan = identity_plan(card, events)
    rows = keyed_rows(card, facts, events, plan)
    connection = duckdb.connect(str(out / "behaviours.duckdb"))
    try:
        create_events(connection)
        connection.executemany(_INSERT, rows)
        aggregate_events(connection)
    finally:
        connection.close()
    return out


def _store_items(run_family_only: bool) -> list[KnowledgeItem]:
    items = [
        KnowledgeItem(
            statement="actor target did execute to shell",
            label="step-run",
            label_kind="known_bad",
            label_basis="attack_step",
            family="fam_run",
            split="build",
            index="runidx",
            source_kind="activity",
            query='search index="runidx" TERM("target") | head 5',
        )
    ]
    if run_family_only:
        return items
    for family, index, actor in (("fam_a", "aidx", "alice"), ("fam_b", "bidx", "bob")):
        items.extend(
            [
                KnowledgeItem(
                    statement=f"actor {actor} did execute to shell",
                    label=f"step-{family}",
                    label_kind="known_bad",
                    label_basis="attack_step",
                    family=family,
                    split="build",
                    index=index,
                    source_kind="activity",
                    query=f'search index="{index}" TERM("{actor}") | head 5',
                ),
                KnowledgeItem(
                    statement=f"actor {actor}-service did read to file",
                    label=f"routine-{family}",
                    label_kind="known_good",
                    label_basis="unlabelled",
                    family=family,
                    split="build",
                    index=index,
                    source_kind="activity",
                    query=f'search index="{index}" TERM("{actor}-service") | head 5',
                ),
            ]
        )
    return items


def _prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_family_only: bool = False
) -> tuple[Path, Path]:
    out = _run_out(tmp_path)
    store = tmp_path / "knowledge.duckdb"
    build_store(_store_items(run_family_only), _Embedder(), store)
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.__main__.embedding_from_env", _Embedder
    )
    monkeypatch.delenv("PORTAL_HUNT_JUDGE_URL", raising=False)
    monkeypatch.delenv("PORTAL_HUNT_JUDGE_MODEL", raising=False)
    return out, store


def test_main_runs_the_real_path_with_an_injected_source_and_lofo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, store = _prepare(tmp_path, monkeypatch)
    search = _RecordingSearch()

    code = main(
        [
            "--index",
            "runidx",
            "--out",
            str(out),
            "--stage",
            "notables",
            "--generators",
            "alerts,peer_rare,deviation,similar_to_known",
            "--family",
            "fam_run",
            "--knowledge-store",
            str(store),
        ],
        search=search,
    )

    assert code == 0
    assert search.queries, "the injected source must be the one the run reads through"
    rows = [
        json.loads(line)
        for line in (out / "notables.jsonl").read_text().splitlines()
        if line.strip()
    ]
    similar = [row for row in rows if row["generator"] == "similar_to_known"]
    assert similar
    for row in similar:
        assert all(item["family"] != "fam_run" for item in row["nearest_known"])
        assert all(item["index"] != "runidx" for item in row["nearest_known"])
    progress = json.loads((out / "progress.json").read_text())
    detail = progress["stages"]["notables"]["similar_to_known"]
    assert detail["excluded_family"] == "fam_run"
    assert detail["loaded_families"] == ["fam_a", "fam_b"]


def test_lofo_infers_excluded_family_from_the_store_when_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, store = _prepare(tmp_path, monkeypatch)
    code = main(
        [
            "--index",
            "runidx",
            "--out",
            str(out),
            "--stage",
            "notables",
            "--generators",
            "similar_to_known",
            "--knowledge-store",
            str(store),
        ],
        search=_RecordingSearch(),
    )

    assert code == 0
    progress = json.loads((out / "progress.json").read_text())
    detail = progress["stages"]["notables"]["similar_to_known"]
    assert detail["excluded_family"] == "fam_run"
    assert detail["loaded_families"] == ["fam_a", "fam_b"]


def test_lofo_guard_holds_on_the_real_run_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, store = _prepare(tmp_path, monkeypatch, run_family_only=True)

    with pytest.raises(KnowledgeError, match="no knowledge items remain"):
        main(
            [
                "--index",
                "runidx",
                "--out",
                str(out),
                "--stage",
                "notables",
                "--generators",
                "similar_to_known",
                "--family",
                "fam_run",
                "--knowledge-store",
                str(store),
            ],
            search=_RecordingSearch(),
        )


def test_main_hunts_an_unseen_index_against_every_store_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run_out(tmp_path)
    store = tmp_path / "knowledge.duckdb"
    items = [item for item in _store_items(False) if item.index != "runidx"]
    build_store(items, _Embedder(), store)
    monkeypatch.setattr(
        "portal.modules.security.core.hunt.notables.__main__.embedding_from_env", _Embedder
    )
    monkeypatch.delenv("PORTAL_HUNT_JUDGE_URL", raising=False)
    monkeypatch.delenv("PORTAL_HUNT_JUDGE_MODEL", raising=False)
    measured = tmp_path / "merge_weights.json"
    measured.write_text(json.dumps({"source": "measured", "weights": {"similar_to_known": 3}}))
    monkeypatch.setenv("PORTAL_HUNT_MERGE_WEIGHTS", str(measured))

    code = main(
        [
            "--index",
            "runidx",
            "--out",
            str(out),
            "--stage",
            "notables",
            "--generators",
            "similar_to_known",
            "--knowledge-store",
            str(store),
        ],
        search=_RecordingSearch(),
    )

    assert code == 0
    progress = json.loads((out / "progress.json").read_text())
    detail = progress["stages"]["notables"]["similar_to_known"]
    assert detail["index_unseen"] is True
    assert detail["excluded_families"] == []
    assert detail["loaded_families"] == ["fam_a", "fam_b"]
    merge = progress["stages"]["notables"]["merge"]
    assert merge["weights_source"] == "measured"
    assert merge["weights"] == {"similar_to_known": 3}
    rows = [
        json.loads(line)
        for line in (out / "notables.jsonl").read_text().splitlines()
        if line.strip()
    ]
    similar = [row for row in rows if row["generator"] == "similar_to_known"]
    assert similar
    for row in similar:
        assert all(item["index"] != "runidx" for item in row["nearest_known"])
    assert "excluded families: none — index unseen by the store" in capsys.readouterr().out


def test_merge_weights_env_parses_a_vector_and_measures_a_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from portal.modules.security.core.hunt.notables.run import merge_weights_from_env

    monkeypatch.delenv("PORTAL_HUNT_MERGE_WEIGHTS", raising=False)
    assert merge_weights_from_env() == (None, "default")
    monkeypatch.setenv("PORTAL_HUNT_MERGE_WEIGHTS", '{"deviation": 26, "alerts": 0}')
    assert merge_weights_from_env() == ({"deviation": 26, "alerts": 0}, "override")
    monkeypatch.setenv("PORTAL_HUNT_MERGE_WEIGHTS", '{"deviation": 1.5}')
    with pytest.raises(ValueError, match="non-negative integer"):
        merge_weights_from_env()

    measured = tmp_path / "merge_weights.json"
    measured.write_text(json.dumps({"source": "measured", "weights": {"deviation": 9}}))
    monkeypatch.setenv("PORTAL_HUNT_MERGE_WEIGHTS", str(measured))
    assert merge_weights_from_env() == ({"deviation": 9}, "measured")
    measured.write_text("{not json")
    with pytest.raises(ValueError, match="is not JSON"):
        merge_weights_from_env()
    monkeypatch.setenv("PORTAL_HUNT_MERGE_WEIGHTS", str(tmp_path / "absent.json"))
    with pytest.raises(ValueError, match="which is not a file"):
        merge_weights_from_env()
