from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

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
