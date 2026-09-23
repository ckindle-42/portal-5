"""Acceptance: sandbox guard, attach+query+profile roundtrip, blocked statements."""

import importlib
from pathlib import Path

import pytest

mod = importlib.import_module("portal.modules.data.tools.data_mcp")


def test_sql_blocklist() -> None:
    out = mod.run_sql("s1", "INSTALL httpfs;")
    assert "blocked" in out.get("error", "")


def test_run_sql_cannot_read_arbitrary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The core sandbox guarantee: even bypassing the regex, the query
    connection has filesystem access disabled."""
    pytest.importorskip("duckdb")
    monkeypatch.setattr(mod, "_ROOT", tmp_path.resolve())
    monkeypatch.setattr(mod, "_SESS_DIR", tmp_path / "sess")
    mod._conns.clear()
    (tmp_path / "seed.csv").write_text("a\n1\n")
    mod.attach_source("sec_test", "seed.csv", "t")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    # regex denylist catches it first
    blocked = mod.run_sql("sec_test", f"SELECT * FROM read_text('{secret}')")
    assert "error" in blocked
    # and even if the denylist were bypassed, DuckDB itself refuses
    con = mod._conn("sec_test")
    with pytest.raises(Exception, match="(?i)external|permission|disabled"):
        con.execute(f"SELECT content FROM read_blob('{secret}')")
    with pytest.raises(Exception, match="(?i)external|Cannot enable"):
        con.execute("SET enable_external_access=true")
    mod._conns.clear()


def test_path_escape_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_ROOT", tmp_path.resolve())
    with pytest.raises(ValueError):
        mod._resolve("../../etc/passwd")


def test_bad_session_id_rejected() -> None:
    with pytest.raises(ValueError):
        mod._conn("../evil")


def test_attach_query_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("duckdb")
    monkeypatch.setattr(mod, "_ROOT", tmp_path.resolve())
    monkeypatch.setattr(mod, "_SESS_DIR", tmp_path / "sess")
    mod._conns.clear()
    csv = tmp_path / "d.csv"
    csv.write_text("a,b\n1,x\n2,y\n3,x\n")
    a = mod.attach_source("sess_test", "d.csv", "t")
    assert a["rows"] == 3
    q = mod.run_sql("sess_test", "SELECT b, count(*) c FROM t GROUP BY b ORDER BY c DESC")
    assert q["row_count"] == 2
    p = mod.profile_table("sess_test", "t")
    assert any(col["column"] == "a" and "mean" in col for col in p["profile"])
    ls = mod.list_session("sess_test")
    assert "t" in ls["tables"]
    mod._conns.clear()


def test_tools_manifest_matches_dispatch() -> None:
    assert {t["function"]["name"] for t in mod.TOOLS_MANIFEST} == set(mod._DISPATCH)


def test_connections_are_memory_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DuckDB defaults to 80% of host RAM per database; every session connection
    must carry the configured cap, and user SQL cannot raise it."""
    pytest.importorskip("duckdb")
    monkeypatch.setattr(mod, "_SESS_DIR", tmp_path / "sess")
    monkeypatch.setitem(mod._LIMITS, "memory_limit", "256MB")
    mod._conns.clear()
    con = mod._conn("mem_test")
    limit = con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert limit.replace(" ", "").upper() in {"256.0MIB", "256MIB", "244.1MIB", "256.0MB"}
    assert "blocked" in mod.run_sql("mem_test", "SET memory_limit='60GB'").get("error", "")
    mod._conns.clear()


def test_connection_cache_evicts_least_recent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("duckdb")
    monkeypatch.setattr(mod, "_SESS_DIR", tmp_path / "sess")
    monkeypatch.setattr(mod, "_MAX_CONNS", 2)
    mod._conns.clear()
    first = mod._conn("s_a")
    mod._conn("s_b")
    mod._conn("s_a")  # touch: s_b is now least recent
    mod._conn("s_c")
    assert list(mod._conns) == ["s_a", "s_c"]
    assert mod._conns["s_a"] is first
    mod._conns.clear()


def _big_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sid: str) -> None:
    monkeypatch.setattr(mod, "_SESS_DIR", tmp_path / "sess")
    mod._conns.clear()
    c = mod._loader_conn(sid)
    c.execute("CREATE TABLE t AS SELECT repeat('x', 40) AS pad FROM range(2000000)")
    c.close()


def test_out_of_memory_is_retried_with_more_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list() cannot spill; the query must succeed without the caller re-running,
    and the connection must drop back to its starting limit afterwards."""
    pytest.importorskip("duckdb")
    _big_session(tmp_path, monkeypatch, "grow")
    monkeypatch.setitem(mod._LIMITS, "memory_limit", "32MB")
    monkeypatch.setattr(mod, "_escalation_ceiling", lambda: 4 * 10**9)
    out = mod.run_sql("grow", "SELECT len(list(pad)) AS n FROM t")
    assert out.get("rows") == [[2000000]], out
    assert out["memory_limit_used_gb"] > 0.032
    limit = mod._conn("grow").execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert "30.5 MiB" in limit or "32" in limit
    mod._conns.clear()


def test_out_of_memory_reports_ceiling_when_host_cannot_spare_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("duckdb")
    _big_session(tmp_path, monkeypatch, "cap")
    monkeypatch.setitem(mod._LIMITS, "memory_limit", "32MB")
    monkeypatch.setattr(mod, "_escalation_ceiling", lambda: 64 * 10**6)
    out = mod.run_sql("cap", "SELECT len(list(pad)) FROM t")
    assert "host can spare" in out.get("error", ""), out
    mod._conns.clear()


def test_memory_size_parsing() -> None:
    assert mod._bytes("4GB") == 4 * 10**9
    assert mod._bytes("512MiB") == 512 * 2**20
    assert mod._bytes("1024") == 1024
