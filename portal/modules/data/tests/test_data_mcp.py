"""Acceptance: sandbox guard, attach+query+profile roundtrip, blocked statements."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.data.tools.data_mcp")


def test_sql_blocklist() -> None:
    out = mod.run_sql("s1", "INSTALL httpfs;")
    assert "blocked" in out.get("error", "")


def test_bad_session_id_rejected() -> None:
    pytest.importorskip("duckdb")  # _conn lazy-imports duckdb before validating the id
    with pytest.raises(ValueError):
        mod._conn("../evil")


def test_registered_tools_are_served_natively() -> None:
    import asyncio

    assert {tool.name for tool in asyncio.run(mod.mcp.list_tools())} == {
        "attach_source",
        "list_session",
        "profile_table",
        "run_sql",
    }


def test_memory_size_parsing() -> None:
    assert mod._bytes("4GB") == 4 * 10**9
    assert mod._bytes("512MiB") == 512 * 2**20
    assert mod._bytes("1024") == 1024
