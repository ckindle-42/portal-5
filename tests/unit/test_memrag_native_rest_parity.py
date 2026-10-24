"""Native tool vs REST route parity for the memory and rag MCP servers.

Both surfaces must return identical output: the native tools and the REST routes
call the same impl functions, so one call through each path against the same
store has to agree byte for byte — including error payloads and eval-scope
handling.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from portal.platform.mcp_host import eval_scope as es

RUN = "wfe_" + "c" * 40
SCOPE = {"campaign": "wfe_" + "d" * 16, "run": RUN, "allow": ["kb_list", "recall"]}


def _post(handler, body):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
    resp = asyncio.run(handler(req))
    return resp.status_code, json.loads(resp.body)


def _endpoint(mcp_server, path):
    """The registered REST handler for a custom route on the server."""
    return next(r.endpoint for r in mcp_server._custom_starlette_routes if r.path == path)


def _native(mcp_server, name, arguments, meta=None):
    """Call a tool through the server's native dispatch (the pipeline's path)."""
    context = SimpleNamespace(
        request_context=SimpleNamespace(params={"_meta": meta if meta is not None else {}})
    )
    result = asyncio.run(mcp_server.call_tool(name, arguments, context))
    assert result.is_error is False
    return json.loads(result.content[0].text)


# ── memory ───────────────────────────────────────────────────────────────────
@pytest.fixture
def memory(tmp_path, monkeypatch):
    import portal.platform.lance_guard as lg
    from portal.platform.memory import graph_memory as m
    from portal.platform.memory import memory_mcp

    monkeypatch.setattr(lg, "require_lance_dir", lambda *a, **k: None)
    monkeypatch.setattr(m, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(m, "_db", None)
    monkeypatch.setattr(m, "_tables", {})

    async def embed(text, role):
        h = hashlib.sha256(text.lower().encode()).digest()
        return [((h[i % 32] / 255.0) - 0.5) for i in range(m.EMBEDDING_DIM)]

    async def version():
        return "stub-v1"

    async def extract(text):
        return {"entities": [("Acme", "org")], "relations": [("Acme", "supplies", "Bolt")]}

    monkeypatch.setattr(m, "_embed", embed)
    monkeypatch.setattr(m, "_version", version)
    monkeypatch.setattr(m, "_extract", extract)
    yield memory_mcp
    es.EVAL_SCOPE.set(None)


def test_memory_native_recall_matches_rest(memory):

    mcp_server = memory.mcp
    status, stored = _post(
        _endpoint(mcp_server, "/tools/remember"),
        {"arguments": {"text": "Acme supplies Bolt", "category": "fact"}},
    )
    assert status == 200 and stored["stored"] is True
    asyncio.run(asyncio.sleep(0.05))  # let the graph ingestion settle

    args = {"query": "Acme supplies Bolt", "hops": 2, "top_k": 5}
    status, rest = _post(_endpoint(mcp_server, "/tools/recall"), {"arguments": args})
    native = _native(mcp_server, "recall", args)
    assert status == 200
    assert native == rest
    assert rest["num_results"] == 1 and rest["memories"][0]["category"] == "fact"

    # the error payload is identical too (the status stays REST-only)
    _, rest_err = _post(_endpoint(mcp_server, "/tools/recall"), {"arguments": {"query": ""}})
    native_err = _native(mcp_server, "recall", {"query": ""})
    assert rest_err == native_err == {"error": "query is required"}


def test_memory_native_scoped_recall_matches_rest_scoped(memory):

    mcp_server = memory.mcp
    rest = _endpoint(mcp_server, "/tools/remember")
    _, _ = _post(rest, {"arguments": {"text": "operator: Acme supplies Bolt"}})
    _, _ = _post(rest, {"arguments": {"text": "eval: Acme supplies Bolt"}, "eval": SCOPE})
    asyncio.run(asyncio.sleep(0.05))

    args = {"query": "eval: Acme supplies Bolt", "hops": 2, "top_k": 5}
    _, rest_scoped = _post(
        _endpoint(mcp_server, "/tools/recall"), {"arguments": args, "eval": SCOPE}
    )
    native_scoped = _native(mcp_server, "recall", args, meta={es.EVAL_META_KEY: SCOPE})
    assert native_scoped == rest_scoped
    assert "eval:" in json.dumps(rest_scoped) and "operator:" not in json.dumps(rest_scoped)


# ── rag ──────────────────────────────────────────────────────────────────────
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
    return rag_mcp, rm, tmp_path


def test_rag_native_kb_list_matches_rest(rag):
    rag_mcp, rm, tmp = rag
    src = tmp / "cip"
    src.mkdir()
    (src / "r.md").write_text("CIP-007 R2 patch management evaluation every 35 days.")
    asyncio.run(rm._pipeline.ingest_document(rm._composition(), "NERC-CIP", src, True))

    mcp_server = rag_mcp.mcp
    status, rest = _post(_endpoint(mcp_server, "/tools/kb_list"), {})
    native = _native(mcp_server, "kb_list", {})
    assert status == 200
    assert native == rest
    assert {k["kb_id"] for k in rest["knowledge_bases"]} == {"NERC-CIP"}


def test_rag_native_scoped_kb_list_matches_rest_scoped(rag):
    rag_mcp, rm, tmp = rag
    seed = es.bind_route(rm._eval_seed_kb)
    status, _ = _post(seed, {"eval": SCOPE, "docs": {"a.md": "fixture text"}})
    assert status == 200

    mcp_server = rag_mcp.mcp
    _, rest_scoped = _post(_endpoint(mcp_server, "/tools/kb_list"), {"eval": SCOPE})
    native_scoped = _native(mcp_server, "kb_list", {}, meta={es.EVAL_META_KEY: SCOPE})
    assert native_scoped == rest_scoped
    assert [k["kb_id"] for k in rest_scoped["knowledge_bases"]] == [RUN]
