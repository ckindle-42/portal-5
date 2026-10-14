"""The RAG MCP under a WFE evaluation scope (root-fix Part 2b), on a real LanceDB in a temp dir
with a deterministic stub embedder: the scope owns the KB, search and search-all never see the
operator's KBs, ingest and maintenance are refused, seeding and dropping are scope-only."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import pytest

from portal.platform.mcp_host import eval_scope as es

RUN = "wfe_" + "a1" * 20
SCOPE = {
    "campaign": "wfe_" + "b2" * 8,
    "run": RUN,
    "allow": ["kb_search", "kb_search_all", "kb_list"],
}


@pytest.fixture
def rag(tmp_path, monkeypatch):
    import portal.platform.lance_guard as lg
    from portal.modules.research.tools import rag_mcp
    from portal.modules.research.tools import rag_multimodal as rm
    from portal.platform.retrieval import embedding as emb
    from portal.platform.retrieval import store

    monkeypatch.setattr(lg, "require_lance_dir", lambda *a, **k: None)
    monkeypatch.setattr(store, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(store, "RAG_DIR", str(tmp_path / "lance" / "rag"))
    monkeypatch.setattr(store, "_db", None)
    monkeypatch.setenv("PORTAL5_KB_SOURCES_DIR", str(tmp_path / "sources"))
    dim = emb.VL_DIM

    async def embed_batch(items):
        out = []
        for it in items:
            v = [0.0] * dim
            for w in re.findall(r"[a-z0-9]+", (it.get("text") or "").lower()):
                v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % dim] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out

    async def model_id():
        return ("stub-vl", dim)

    async def rerank(query, candidates, top_n):
        return [{"index": i, "score": 0.5} for i in range(min(top_n, len(candidates)))]

    monkeypatch.setattr(emb, "vl_embed_batch", embed_batch)
    monkeypatch.setattr(emb, "vl_model_id", model_id)
    monkeypatch.setattr(emb, "vl_rerank", rerank)
    return rm, rag_mcp, store, tmp_path


def _post(handler, body):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
    resp = asyncio.run(handler(req))
    return resp.status_code, json.loads(resp.body)


def _operator_kb(rm, tmp_path):
    src = tmp_path / "op_src"
    src.mkdir()
    (src / "secret.md").write_text(
        "Operator confidential: the substation relay setpoint is 77 amps."
    )
    asyncio.run(rm._pipeline.ingest_document(rm._composition(), "opkb", src, True))


def test_the_scope_owns_the_kb_and_never_sees_the_operators(rag):
    rm, _, store, tmp = rag
    _operator_kb(rm, tmp)
    seed = es.bind_route(rm._eval_seed_kb)
    status, body = _post(
        seed, {"eval": SCOPE, "docs": {"facts.md": "Fixture: the relay setpoint is 42 amps."}}
    )
    assert status == 200, body
    assert {"opkb", RUN} <= set(store.list_kbs())  # not vacuous: both KBs exist
    search = es.bind_route(rm._search)
    _, hit = _post(
        search, {"arguments": {"kb_id": "opkb", "query": "relay setpoint"}, "eval": SCOPE}
    )
    assert "42 amps" in json.dumps(hit) and "77 amps" not in json.dumps(hit)
    _, every = _post(
        es.bind_route(rm._search_all),
        {"arguments": {"query": "relay setpoint amps"}, "eval": SCOPE},
    )
    assert "42 amps" in json.dumps(every) and "77 amps" not in json.dumps(every)
    _, op = _post(search, {"arguments": {"kb_id": "opkb", "query": "relay setpoint"}})
    assert "77 amps" in json.dumps(op)  # without a scope nothing changes


def test_ingest_and_maintenance_are_refused_under_a_scope(rag):
    rm, rag_mcp, _, tmp = rag
    status, _ = _post(
        es.bind_route(rm._ingest),
        {"arguments": {"kb_id": "x", "source_dir": str(tmp)}, "eval": SCOPE},
    )
    assert status == 403
    for ep in (
        rag_mcp.kb_optimize_endpoint,
        rag_mcp.kb_versions_endpoint,
        rag_mcp.kb_restore_endpoint,
    ):
        assert _post(ep, {"arguments": {"kb_id": "opkb"}, "eval": SCOPE})[0] == 403


def test_kb_list_shows_only_the_runs_kb_under_a_scope(rag):
    rm, rag_mcp, _, tmp = rag
    _operator_kb(rm, tmp)
    _post(es.bind_route(rm._eval_seed_kb), {"eval": SCOPE, "docs": {"a.md": "fixture text"}})
    _, scoped = _post(rag_mcp.kb_list_endpoint, {"eval": SCOPE})
    _, full = _post(rag_mcp.kb_list_endpoint, {})
    assert [k["kb_id"] for k in scoped["knowledge_bases"]] == [RUN]
    assert {"opkb", RUN} <= {k["kb_id"] for k in full["knowledge_bases"]}


def test_seed_names_are_checked_and_drop_is_scope_only(rag):
    rm, _, store, tmp = rag
    _operator_kb(rm, tmp)
    seed, drop = es.bind_route(rm._eval_seed_kb), es.bind_route(rm._eval_drop_kb)
    assert _post(seed, {"eval": SCOPE, "docs": {"../escape.md": "x"}})[0] == 400
    assert _post(seed, {"docs": {"a.md": "x"}})[0] == 400
    _post(seed, {"eval": SCOPE, "docs": {"a.md": "fixture text"}})
    assert _post(drop, {})[0] == 400
    status, body = _post(drop, {"eval": SCOPE})
    assert status == 200 and store.tname(RUN) in body["dropped"]
    assert RUN not in store.list_kbs() and "opkb" in store.list_kbs()
    assert not (tmp / "sources" / "wfe" / SCOPE["campaign"] / RUN).exists()
