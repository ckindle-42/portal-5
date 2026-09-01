"""Acceptance: graph-backed recall replaces flat recall; contracts intact; migration runs."""

import asyncio
import importlib
import json

import pytest

gm = importlib.import_module("portal.platform.memory.graph_memory")


class _Req:
    def __init__(self, a):
        self._a = {"arguments": a}

    async def json(self):
        return self._a


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "LANCE_DIR", str(tmp_path))
    gm._db = None
    gm._tables.clear()

    async def _emb(t):
        return [0.0] * gm.EMBEDDING_DIM

    async def _ext(t):
        return {
            "entities": [["PLC-21", "asset"], ["CIP-007", "standard"]],
            "relations": [["PLC-21", "governed_by", "CIP-007"]],
        }

    monkeypatch.setattr(gm, "_embed", _emb)
    monkeypatch.setattr(gm, "_extract", _ext)


def test_remember_populates_graph():
    pytest.importorskip("lancedb")
    out = json.loads(_run(gm._remember(_Req({"text": "PLC-21 is governed by CIP-007"}))).body)
    assert out["stored"] and out["graph_updated"]
    assert out["category"] == "fact"  # contract preserved
    assert len(gm._relations()) >= 1


def test_recall_is_graph_aware_and_contract_intact():
    pytest.importorskip("lancedb")
    _run(gm._remember(_Req({"text": "PLC-21 is governed by CIP-007"})))
    out = json.loads(_run(gm._recall(_Req({"query": "PLC-21"}))).body)
    # preserved contract keys
    assert {"query", "num_results", "memories"} <= set(out)
    # new graph context
    assert "graph_context" in out
    assert "CIP-007" in out["graph_context"]["nodes"]


def test_forget_and_list_contract():
    pytest.importorskip("lancedb")
    mid = json.loads(_run(gm._remember(_Req({"text": "a fact about X"}))).body)["id"]
    lst = json.loads(_run(gm._list_memories(_Req({}))).body)
    assert lst["total"] >= 1 and "memories" in lst
    fg = json.loads(_run(gm._forget(_Req({"id": mid}))).body)
    assert fg["deleted"] is True and fg["id"] == mid


def test_neighbors_and_timeline():
    pytest.importorskip("lancedb")
    _run(gm._remember(_Req({"text": "PLC-21 is governed by CIP-007"})))
    nb = json.loads(_run(gm._neighbors(_Req({"name": "PLC-21"}))).body)
    assert "CIP-007" in nb["nodes"]
    tl = json.loads(_run(gm._entity_timeline(_Req({"name": "CIP-007"}))).body)
    assert tl["event_count"] >= 1


def test_link_adds_edge():
    pytest.importorskip("lancedb")
    out = json.loads(_run(gm._link(_Req({"src": "A", "dst": "B", "rel_type": "depends_on"}))).body)
    assert out["linked"] is True


def test_migration_runs():
    pytest.importorskip("lancedb")
    _run(gm._remember(_Req({"text": "seed memory one"})))
    _run(gm._remember(_Req({"text": "seed memory two"})))
    res = _run(gm.migrate_existing())
    assert res["migrated"] >= 2


def test_graph_stats_detects_restore_shortfall(tmp_path, monkeypatch):
    """C2: memories present but no graph tables == a restore that lost the
    entity/relation tables. graph_stats reports graph_intact False, and never
    creates the missing tables as a side effect."""
    pytest.importorskip("lancedb")
    import lancedb
    import pyarrow as pa

    monkeypatch.setattr(gm, "LANCE_DIR", str(tmp_path))
    gm._db = None
    gm._tables.clear()
    db = lancedb.connect(str(tmp_path))
    db.create_table(
        gm.MEMORY_TABLE,
        schema=pa.schema([pa.field("id", pa.string()), pa.field("text", pa.string())]),
    ).add([{"id": "a", "text": "orphan memory"}])

    s = gm.graph_stats()
    assert s["memories"] == 1 and s["entities"] == 0
    assert s["graph_intact"] is False
    assert set(db.table_names()) == {gm.MEMORY_TABLE}  # not created as a side effect


def test_graph_stats_intact_after_remember():
    pytest.importorskip("lancedb")
    _run(gm._remember(_Req({"text": "PLC-21 is governed by CIP-007"})))
    s = gm.graph_stats()
    assert s["memories"] >= 1 and s["entities"] >= 1 and s["graph_intact"] is True


def test_registration_owns_all_routes():
    calls = []

    class F:
        def custom_route(self, p, methods=None):
            def d(fn):
                calls.append(p)
                return fn

            return d

    gm.register_memory_routes(F())
    for ep in (
        "/tools/remember",
        "/tools/recall",
        "/tools/graph_recall",
        "/tools/neighbors",
        "/tools/entity_timeline",
        "/tools/link",
    ):
        assert ep in calls
