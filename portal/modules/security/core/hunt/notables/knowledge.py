"""Provenance-carrying labelled behaviours persisted with Pipeline embeddings."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import duckdb

from .embedding import EmbeddingError, embed_batches, embedding_from_env, embedding_requirement

SCHEMA_VERSION = "2"
ROLE_WORDS = frozenset({"actor", "program", "did", "to"})  # words that only name a role
LABEL_KINDS = frozenset({"known_bad", "known_good"})
GOOD_BASES = frozenset({"unlabelled", "non_attack_day"})
BAD_BASES = frozenset({"attack_step", "technique"})
PROOF_INDEXES = frozenset(
    {"wheeler", "hb_ait_wheeler", "cloudobs_aws", "hb_cloudobs_aws", "botsv1"}
)
ATTACK_ONLY_INDEXES = frozenset(
    {"labelled_corpus", "portal5_lab", "attack_data_refresh", "attack_data_refresh_20261107"}
)


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class KnowledgeError(RuntimeError):
    """The knowledge manifest or persisted store violates its contract."""


@dataclass(frozen=True)
class KnowledgeItem:
    """One normalized behaviour label and the query that reproduces its events."""

    statement: str
    label: str
    label_kind: str
    label_basis: str
    family: str
    split: str
    index: str
    source_kind: str
    query: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> KnowledgeItem:
        item = cls(
            statement=str(raw.get("statement") or "").strip(),
            label=str(raw.get("label") or "").strip(),
            label_kind=str(raw.get("label_kind") or "").strip(),
            label_basis=str(raw.get("label_basis") or "").strip(),
            family=str(raw.get("family") or "").strip(),
            split=str(raw.get("split") or "").strip(),
            index=str(raw.get("index") or "").strip(),
            source_kind=str(raw.get("source_kind") or "").strip(),
            query=str(raw.get("query") or "").strip(),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if not all(
            (
                self.statement,
                self.label,
                self.family,
                self.split,
                self.index,
                self.source_kind,
                self.query,
            )
        ):
            raise KnowledgeError(
                "each knowledge item needs statement, label, family, split, index, source_kind, and query"
            )
        if self.split != "build":
            raise KnowledgeError("the knowledge store accepts build-split items only")
        index_name = self.index.casefold()
        if index_name in PROOF_INDEXES:
            raise KnowledgeError(f"proof index {self.index!r} cannot enter the knowledge store")
        if self.label_kind not in LABEL_KINDS:
            raise KnowledgeError(f"unsupported knowledge label kind: {self.label_kind!r}")
        if self.label_kind == "known_good" and index_name in ATTACK_ONLY_INDEXES:
            raise KnowledgeError(
                f"attack-only index {self.index!r} cannot provide known-good knowledge"
            )
        bases = GOOD_BASES if self.label_kind == "known_good" else BAD_BASES
        if self.label_basis not in bases:
            raise KnowledgeError(
                f"invalid {self.label_kind} provenance basis: {self.label_basis!r}"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "statement": self.statement,
            "label": self.label,
            "label_kind": self.label_kind,
            "label_basis": self.label_basis,
            "family": self.family,
            "split": self.split,
            "index": self.index,
            "source_kind": self.source_kind,
            "query": self.query,
        }


@dataclass
class LoadedKnowledge:
    """A DuckDB connection with the leave-one-family-out view already materialized."""

    connection: duckdb.DuckDBPyConnection
    run_index: str
    excluded_families: tuple[str, ...]
    allowed_families: tuple[str, ...] | None
    families: tuple[str, ...]
    items: int
    embedding_model: str
    dimensions: int
    contradicted: int = 0
    uninformative: int = 0
    index_unseen: bool = False

    @property
    def excluded_family(self) -> str:
        return (
            self.excluded_families[0]
            if len(self.excluded_families) == 1
            else ",".join(self.excluded_families)
        )


def statement_has_content(statement: str) -> bool:
    """True when a statement names something beyond role words and masked tokens."""
    return any(
        token.strip("*") for token in statement.split() if token.casefold() not in ROLE_WORDS
    )


def _item_id(item: KnowledgeItem) -> str:
    body = json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _unit_vector(raw: Sequence[float], expected: int | None = None) -> list[float]:
    vector = [float(value) for value in raw]
    if not vector or (expected is not None and len(vector) != expected):
        raise KnowledgeError("embedding dimensions differ or are empty")
    if not all(math.isfinite(value) for value in vector):
        raise KnowledgeError("embedding contains a non-finite value")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise KnowledgeError("embedding has zero length")
    return [value / norm for value in vector]


def build_store(
    items: Sequence[KnowledgeItem], embedder: Embedder, store_path: Path
) -> dict[str, Any]:
    """Embed distinct statements and atomically replace the DuckDB knowledge store."""
    unique: dict[str, KnowledgeItem] = {}
    for item in items:
        item.validate()
        unique.setdefault(_item_id(item), item)
    material = sorted(unique.values(), key=_item_id)
    if not material:
        raise KnowledgeError("knowledge manifest has no items")
    statements = list(dict.fromkeys(item.statement for item in material))
    statement_indexes = {statement: index for index, statement in enumerate(statements)}
    family_names = sorted({item.family for item in material})
    manifest_digest = hashlib.sha256(
        "\n".join(
            json.dumps(item.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in material
        ).encode("utf-8")
    ).hexdigest()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = store_path.with_name(f".{store_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        dimensions = _write_store(
            temporary,
            material,
            statement_indexes,
            statements,
            embedder,
            embedder.model,
            family_names,
            manifest_digest,
        )
        from .verdicts import carry_verdicts

        carry_verdicts(store_path, temporary)
        os.replace(temporary, store_path)
    finally:
        temporary.unlink(missing_ok=True)
        temporary.with_name(temporary.name + ".wal").unlink(missing_ok=True)
    stats = getattr(embedder, "stats", None)
    return {
        "store": str(store_path),
        "items": len(material),
        "unique_statements": len(statements),
        "families": family_names,
        "embedding_model": embedder.model,
        "dimensions": dimensions,
        "manifest_sha256": manifest_digest,
        "embedding": stats() if callable(stats) else {},
    }


def _write_store(
    path: Path,
    items: Sequence[KnowledgeItem],
    statement_indexes: Mapping[str, int],
    statements: Sequence[str],
    embedder: Embedder,
    model: str,
    families: Sequence[str],
    manifest_digest: str,
) -> int:
    """Stream embeddings into DuckDB, then publish the complete metadata and vector tables."""
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            "CREATE TABLE item_manifest (item_id VARCHAR, statement VARCHAR, label VARCHAR, "
            "label_kind VARCHAR, label_basis VARCHAR, family VARCHAR, split VARCHAR, "
            "index_name VARCHAR, source_kind VARCHAR, provenance_query VARCHAR, statement_index INTEGER)"
        )
        connection.executemany(
            "INSERT INTO item_manifest VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    _item_id(item),
                    item.statement,
                    item.label,
                    item.label_kind,
                    item.label_basis,
                    item.family,
                    item.split,
                    item.index,
                    item.source_kind,
                    item.query,
                    statement_indexes[item.statement],
                )
                for item in items
            ],
        )
        dimensions = _write_vectors(connection, statements, embedder)
        connection.execute(
            "CREATE TABLE knowledge_items (item_id VARCHAR PRIMARY KEY, statement VARCHAR, "
            "label VARCHAR, label_kind VARCHAR, label_basis VARCHAR, family VARCHAR, split VARCHAR, "
            "index_name VARCHAR, source_kind VARCHAR, provenance_query VARCHAR, "
            f"embedding FLOAT[{dimensions}])"
        )
        connection.execute(
            "INSERT INTO knowledge_items SELECT m.item_id,m.statement,m.label,m.label_kind,"
            "m.label_basis,m.family,m.split,m.index_name,m.source_kind,m.provenance_query,v.embedding "
            "FROM item_manifest m JOIN statement_vectors v USING (statement_index) "
            "ORDER BY m.item_id"
        )
        connection.execute("DROP TABLE item_manifest")
        connection.execute("DROP TABLE statement_vectors")
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "embedding_model": model,
            "dimensions": str(dimensions),
            "items": str(len(items)),
            "families": json.dumps(list(families)),
            "manifest_sha256": manifest_digest,
        }
        connection.execute("CREATE TABLE knowledge_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
        connection.executemany("INSERT INTO knowledge_meta VALUES (?,?)", list(metadata.items()))
    finally:
        connection.close()
    return dimensions


def _write_vectors(
    connection: duckdb.DuckDBPyConnection, statements: Sequence[str], embedder: Embedder
) -> int:
    """Persist one bounded embedding batch at a time and verify ordered completeness."""
    dimensions: int | None = None
    next_index = 0
    for start, batch in embed_batches(embedder, statements):
        if start != next_index or not batch:
            raise KnowledgeError(f"embedding batches are out of order at item {next_index}")
        dimensions = dimensions or len(batch[0])
        if dimensions <= 0:
            raise KnowledgeError("embedding dimensions are empty")
        if next_index == 0:
            connection.execute(
                "CREATE TABLE statement_vectors (statement_index INTEGER PRIMARY KEY, "
                f"embedding FLOAT[{dimensions}])"
            )
        rows = [
            (start + offset, _unit_vector(vector, dimensions))
            for offset, vector in enumerate(batch)
        ]
        connection.executemany(
            f"INSERT INTO statement_vectors VALUES (?, CAST(? AS FLOAT[{dimensions}]))",
            rows,
        )
        next_index += len(batch)
    if dimensions is None or next_index != len(statements):
        raise KnowledgeError(f"asked for {len(statements)} embeddings, got {next_index}")
    return dimensions


def _label_quality_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """Declare the statements a store cannot use as a reference, and the ones worth embedding."""
    contradicted = [
        str(row[0])
        for row in connection.execute(
            "SELECT statement FROM knowledge_items GROUP BY 1 HAVING count(DISTINCT label_kind) > 1"
        ).fetchall()
    ]
    informative = [
        str(row[0])
        for row in connection.execute("SELECT DISTINCT statement FROM knowledge_items").fetchall()
        if statement_has_content(str(row[0]))
    ]
    connection.execute(
        "CREATE TEMP TABLE contradicted_statements AS SELECT unnest(?::VARCHAR[]) AS statement",
        [contradicted],
    )
    connection.execute(
        "CREATE TEMP TABLE informative_statements AS SELECT unnest(?::VARCHAR[]) AS statement",
        [informative],
    )


def _load_conditions(excluded_families: Sequence[str], run_index: str) -> list[str]:
    """The store rows one run may read: its own family and unusable labels removed."""
    conditions = ["split = 'build'"]
    if excluded_families:
        conditions.append("family NOT IN (" + ",".join("?" for _ in excluded_families) + ")")
    conditions.extend(
        [
            "index_name <> ?",
            "statement NOT IN (SELECT statement FROM contradicted_statements)",
            "statement IN (SELECT statement FROM informative_statements)",
        ]
    )
    return conditions


def _label_quality_counts(
    connection: duckdb.DuckDBPyConnection,
    excluded_families: Sequence[str],
    run_index: str,
) -> tuple[int, int]:
    """How many otherwise-loadable items each label rule removes, counted once each."""
    _label_quality_tables(connection)
    conditions = _load_conditions(excluded_families, run_index)
    base_where = " AND ".join(conditions[:-2])  # all but the two label-quality clauses
    parameters = [*excluded_families, run_index]
    contradicted = _excluded_count(
        connection,
        base_where,
        parameters,
        "statement IN (SELECT statement FROM contradicted_statements)",
    )
    uninformative = _excluded_count(
        connection,
        base_where,
        parameters,
        "statement NOT IN (SELECT statement FROM contradicted_statements) "
        "AND statement NOT IN (SELECT statement FROM informative_statements)",
    )
    return contradicted, uninformative


def _excluded_count(
    connection: duckdb.DuckDBPyConnection,
    base_where: str,
    parameters: Sequence[Any],
    condition: str,
) -> int:
    """How many otherwise-loadable items one declared exclusion removes."""
    row = connection.execute(
        f"SELECT count(*) FROM knowledge_items WHERE {base_where} AND {condition}",
        list(parameters),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _run_exclusions(
    connection: duckdb.DuckDBPyConnection, run_index: str, expected_family: str | None
) -> tuple[tuple[str, ...], bool]:
    """Families the run must not learn from, and whether the store has never seen its index."""
    family_rows = connection.execute(
        "SELECT DISTINCT family FROM knowledge_items "
        "WHERE index_name = ? AND split = 'build' ORDER BY family",
        [run_index],
    ).fetchall()
    excluded = tuple(str(row[0]) for row in family_rows)
    if excluded:
        if expected_family and expected_family not in excluded:
            raise KnowledgeError(
                f"run index {run_index!r} belongs to {excluded}, not {expected_family!r}"
            )
        return excluded, False
    if expected_family:
        stored = {
            str(row[0])
            for row in connection.execute("SELECT DISTINCT family FROM knowledge_items").fetchall()
        }
        if expected_family in stored:
            return (expected_family,), True
    return (), True


@contextmanager
def load_for_run(
    store_path: Path,
    *,
    run_index: str,
    expected_family: str | None = None,
    allowed_families: Sequence[str] | None = None,
) -> Iterator[LoadedKnowledge]:
    """Materialize and assert the per-run filtered store; an index unseen by it excludes no family."""
    if not run_index:
        raise ValueError("the run index is required")
    if not store_path.is_file():
        raise FileNotFoundError(f"knowledge store not found: {store_path}")
    connection = duckdb.connect(str(store_path), read_only=True)
    try:
        metadata = dict(connection.execute("SELECT key, value FROM knowledge_meta").fetchall())
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise KnowledgeError("unsupported knowledge store schema")
        excluded_families, index_unseen = _run_exclusions(connection, run_index, expected_family)
        families = None if allowed_families is None else tuple(sorted(set(allowed_families)))
        conditions = _load_conditions(excluded_families, run_index)
        parameters: list[Any] = [*excluded_families, run_index]
        if families is not None:
            if not families:
                raise ValueError("at least one allowed knowledge family is required")
            conditions.append("family IN (" + ",".join("?" for _ in families) + ")")
            parameters.extend(families)
        contradicted_items, uninformative_items = _label_quality_counts(
            connection, excluded_families, run_index
        )
        connection.execute(
            "CREATE TEMP TABLE loaded_knowledge AS SELECT * FROM knowledge_items WHERE "
            + " AND ".join(conditions),
            parameters,
        )
        count_row = connection.execute("SELECT count(*) FROM loaded_knowledge").fetchone()
        leak_where = "index_name = ?"
        leak_parameters: list[Any] = [run_index]
        if excluded_families:
            leak_where = (
                "family IN (" + ",".join("?" for _ in excluded_families) + ") OR " + leak_where
            )
            leak_parameters = [*excluded_families, run_index]
        leaked_row = connection.execute(
            "SELECT count(*) FROM loaded_knowledge WHERE " + leak_where, leak_parameters
        ).fetchone()
        if count_row is None or leaked_row is None:
            raise KnowledgeError("knowledge store count query returned no row")
        count, leaked = int(count_row[0]), int(leaked_row[0])
        if leaked:
            raise KnowledgeError(f"leave-one-family-out violation: {leaked} test items loaded")
        if count == 0:
            raise KnowledgeError("no knowledge items remain after family exclusions")
        loaded_families = tuple(
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT family FROM loaded_knowledge ORDER BY family"
            ).fetchall()
        )
        yield LoadedKnowledge(
            connection,
            run_index,
            excluded_families,
            families,
            loaded_families,
            count,
            str(metadata["embedding_model"]),
            int(metadata["dimensions"]),
            contradicted=contradicted_items,
            uninformative=uninformative_items,
            index_unseen=index_unseen,
        )
    finally:
        connection.close()


def read_manifest(path: Path) -> list[KnowledgeItem]:
    """Read provenance-carrying normalized behaviour records from JSON Lines."""
    items: list[KnowledgeItem] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as exc:
            raise KnowledgeError(f"manifest line {line_number} is not JSON") from exc
        if not isinstance(raw, Mapping):
            raise KnowledgeError(f"manifest line {line_number} is not an object")
        try:
            items.append(KnowledgeItem.from_mapping(raw))
        except KnowledgeError as exc:
            raise KnowledgeError(f"manifest line {line_number}: {exc}") from exc
    return items


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help=(
            "build-only labelled behaviour JSONL: statement,label,label_kind,label_basis,family,"
            "split,index,source_kind,query"
        ),
    )
    parser.add_argument("--store", type=Path, required=True, help="DuckDB output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    embedder = embedding_from_env()
    if embedder is None:
        print(embedding_requirement(), file=sys.stderr)
        return 2
    try:
        receipt = build_store(read_manifest(args.manifest), embedder, args.store)
        receipt_path = args.store.with_suffix(".receipt.json")
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print(json.dumps(receipt, sort_keys=True))
    except (OSError, KnowledgeError, EmbeddingError) as exc:
        print(f"knowledge store build failed: {exc}", file=sys.stderr)
        return 1
    finally:
        embedder.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
