from __future__ import annotations

from pathlib import Path

import pytest

from portal.modules.security.core.hunt.notables.knowledge import (
    KnowledgeError,
    KnowledgeItem,
    build_store,
    load_for_run,
)


class _Embedder:
    model = "unit-embedding-model"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), 1.0] for index, _text in enumerate(texts)]


def _items() -> list[KnowledgeItem]:
    return (
        [
            KnowledgeItem(
                statement=f"actor={index} action=execute object=shell",
                label=f"step-{index}",
                label_kind="known_bad",
                label_basis="attack_step",
                family="ait",
                split="build",
                index="santos",
                source_kind="activity",
                query=f'search index="santos" TERM("actor-{index}") | head 5',
            )
            for index in range(2)
        ]
        + [
            KnowledgeItem(
                statement=f"actor={index} action=read object=file",
                label=f"normal-{index}",
                label_kind="known_good",
                label_basis="unlabelled",
                family="ait",
                split="build",
                index="santos",
                source_kind="activity",
                query=f'search index="santos" TERM("normal-{index}") | head 5',
            )
            for index in range(2)
        ]
        + [
            KnowledgeItem(
                statement="actor=user action=execute object=tool",
                label="step-1",
                label_kind="known_bad",
                label_basis="attack_step",
                family="kyoushi",
                split="build",
                index="kyoushi",
                source_kind="activity",
                query='search index="kyoushi" TERM("user") | head 5',
            )
        ]
    )


def test_store_round_trip_preserves_labels_vectors_and_provenance(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.duckdb"
    receipt = build_store(_items(), _Embedder(), store)

    assert receipt["items"] == 5
    assert receipt["embedding_model"] == "unit-embedding-model"
    with load_for_run(store, run_index="kyoushi") as loaded:
        rows = loaded.connection.execute(
            "SELECT statement, label, label_kind, label_basis, family, index_name, source_kind, "
            "provenance_query, embedding FROM loaded_knowledge ORDER BY item_id"
        ).fetchall()

    assert len(rows) == 4
    statement, label, label_kind, basis, family, index_name, source_kind, query, vector = rows[0]
    assert statement and label
    assert label_kind in {"known_bad", "known_good"}
    assert basis == ("attack_step" if label_kind == "known_bad" else "unlabelled")
    assert family == "ait"
    assert index_name == "santos"
    assert source_kind == "activity"
    assert query.startswith('search index="santos"')
    assert len(vector) == 2


def test_run_loader_excludes_the_test_family_on_its_store_read_path(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.duckdb"
    build_store(_items(), _Embedder(), store)

    with load_for_run(
        store,
        run_index="kyoushi",
        allowed_families=("ait", "kyoushi"),
    ) as loaded:
        families = {
            row[0]
            for row in loaded.connection.execute(
                "SELECT DISTINCT family FROM loaded_knowledge"
            ).fetchall()
        }

    assert "ait" in families
    assert "kyoushi" not in families


def test_run_loader_excludes_every_index_in_a_shared_family(tmp_path: Path) -> None:
    items = _items()
    items.append(
        KnowledgeItem(
            statement="actor=operator action=write object=service",
            label="step-russell",
            label_kind="known_bad",
            label_basis="attack_step",
            family="ait",
            split="build",
            index="russellmitchell",
            source_kind="activity",
            query='search index="russellmitchell" TERM("operator") | head 5',
        )
    )
    store = tmp_path / "shared-family.duckdb"
    build_store(items, _Embedder(), store)

    with load_for_run(
        store,
        run_index="santos",
        expected_family="ait",
        allowed_families=("ait", "kyoushi"),
    ) as loaded:
        indexes = {
            row[0]
            for row in loaded.connection.execute(
                "SELECT DISTINCT index_name FROM loaded_knowledge"
            ).fetchall()
        }

    assert loaded.excluded_families == ("ait",)
    assert indexes == {"kyoushi"}


def test_run_loader_rejects_a_family_claim_that_disagrees_with_the_stored_index(
    tmp_path: Path,
) -> None:
    store = tmp_path / "knowledge.duckdb"
    build_store(_items(), _Embedder(), store)

    with (
        pytest.raises(KnowledgeError, match="belongs to"),
        load_for_run(store, run_index="kyoushi", expected_family="ait"),
    ):
        pass


def test_proof_split_items_cannot_enter_the_persistent_store(tmp_path: Path) -> None:
    proof_item = KnowledgeItem(
        statement="actor=user did action",
        label="step",
        label_kind="known_bad",
        label_basis="attack_step",
        family="proof",
        split="proof",
        index="proof-index",
        source_kind="activity",
        query='search index="proof-index" | head 5',
    )

    with pytest.raises(KnowledgeError, match="build-split"):
        build_store([proof_item], _Embedder(), tmp_path / "knowledge.duckdb")


def test_proof_indexes_cannot_enter_the_persistent_store(tmp_path: Path) -> None:
    proof_item = KnowledgeItem(
        statement="actor=user did execute to shell",
        label="step",
        label_kind="known_bad",
        label_basis="attack_step",
        family="proof",
        split="build",
        index="botsv1",
        source_kind="activity",
        query='search index="botsv1" | head 5',
    )

    with pytest.raises(KnowledgeError, match="proof index"):
        build_store([proof_item], _Embedder(), tmp_path / "knowledge.duckdb")


def test_attack_only_indexes_cannot_supply_known_good(tmp_path: Path) -> None:
    attack_only_item = KnowledgeItem(
        statement="actor=service action=read object=file",
        label="routine",
        label_kind="known_good",
        label_basis="unlabelled",
        family="attack_data",
        split="build",
        index="labelled_corpus",
        source_kind="activity",
        query='search index="labelled_corpus" | head 5',
    )

    with pytest.raises(KnowledgeError, match="cannot provide known-good"):
        build_store([attack_only_item], _Embedder(), tmp_path / "knowledge.duckdb")
