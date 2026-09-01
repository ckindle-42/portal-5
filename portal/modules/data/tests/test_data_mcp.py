"""Acceptance: sandbox guard, attach+query+profile roundtrip, blocked statements."""

import importlib

import pytest

mod = importlib.import_module("portal.modules.data.tools.data_mcp")


def test_sql_blocklist():
    out = mod.run_sql("s1", "INSTALL httpfs;")
    assert "blocked" in out.get("error", "")


def test_path_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_ROOT", tmp_path.resolve())
    with pytest.raises(ValueError):
        mod._resolve("../../etc/passwd")


def test_bad_session_id_rejected():
    with pytest.raises(ValueError):
        mod._conn("../evil")


def test_attach_query_profile(tmp_path, monkeypatch):
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


def test_tools_manifest_matches_dispatch():
    assert {t["function"]["name"] for t in mod.TOOLS_MANIFEST} == set(mod._DISPATCH)
