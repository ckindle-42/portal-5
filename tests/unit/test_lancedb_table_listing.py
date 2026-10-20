"""A5: the shared table-listing helper follows list_tables() pagination without deprecation."""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from portal.platform.lance_guard import list_all_table_names


class _Page:
    def __init__(self, tables: list[str], page_token: str | None) -> None:
        self.tables = tables
        self.page_token = page_token


class _PagedDB:
    """Two-page catalog: three tables, two per page, in the API's response shape."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def list_tables(self, page_token: str | None = None, limit: int | None = None) -> _Page:
        self.calls.append(page_token)
        if page_token is None:
            return _Page(["a", "b"], "tok-1")
        assert page_token == "tok-1"
        return _Page(["c"], None)


class _StuckDB:
    def list_tables(self, page_token: str | None = None, limit: int | None = None) -> _Page:
        return _Page(["a"], "tok-1")


def test_follows_two_pages() -> None:
    db = _PagedDB()
    assert list_all_table_names(db) == ["a", "b", "c"]
    assert db.calls == [None, "tok-1"]


def test_raises_no_deprecation_warning_on_a_real_store(tmp_path: Any) -> None:
    lancedb = pytest.importorskip("lancedb")
    import pyarrow as pa  # type: ignore[import-untyped]

    db = lancedb.connect(str(tmp_path))
    schema = pa.schema([pa.field("id", pa.string())])
    for name in ("t_alpha", "t_beta"):
        db.create_table(name, schema=schema)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert list_all_table_names(db) == ["t_alpha", "t_beta"]
    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


def test_rejects_a_token_that_does_not_advance() -> None:
    with pytest.raises(RuntimeError, match="did not advance"):
        list_all_table_names(_StuckDB())
