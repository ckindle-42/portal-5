"""Graph memory under a WFE evaluation scope (root-fix Part 2b), on a real LanceDB in a temp
dir with deterministic stub embeddings: isolation, scoped forget, filter-injection refusal
(N-27), scoped cleanup, no cross-user graph expansion."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from portal.platform.mcp_host import eval_scope as es

RUN = "wfe_" + "e" * 40
SCOPE = {"campaign": "wfe_" + "f" * 16, "run": RUN, "allow": []}


@pytest.fixture
def gm(tmp_path, monkeypatch):
    import portal.platform.lance_guard as lg
    from portal.platform.memory import graph_memory as m

    monkeypatch.setattr(lg, "require_lance_dir", lambda *a, **k: None)
    monkeypatch.setattr(m, "LANCE_DIR", str(tmp_path / "lance"))
    monkeypatch.setattr(m, "_db", None)
    monkeypatch.setattr(
        m, "_tables", {}
    )  # table handles are cached per process: a fresh DB each test

    async def embed(text, role):
        h = hashlib.sha256(text.lower().encode()).digest()
        return [((h[i % 32] / 255.0) - 0.5) for i in range(m.EMBEDDING_DIM)]

    async def version():
        return "stub-v1"

    async def extract(text):  # _extract returns normalised tuples (see _norm_entity/_norm_relation)
        return {
            "entities": [("Acme", "org"), ("Bolt", "org")],
            "relations": [("Acme", "supplies", "Bolt")],
        }

    monkeypatch.setattr(m, "_embed", embed)
    monkeypatch.setattr(m, "_version", version)
    monkeypatch.setattr(m, "_extract", extract)
    yield m
    es.EVAL_SCOPE.set(None)


def _call(m, handler, args, scoped=False):
    from starlette.requests import Request

    body = {"arguments": args, **({"eval": SCOPE} if scoped else {})}

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)

    async def go():
        resp = await m._scoped(handler)(req)
        await asyncio.sleep(0.05)  # let background graph ingestion finish
        return resp

    resp = asyncio.run(go())
    return resp.status_code, json.loads(resp.body)


def _rows(m, table):
    return table().search().limit(1000).to_list()


def test_a_run_and_the_operator_cannot_see_each_other(gm):
    _call(gm, gm._remember, {"text": "operator: Acme supplies Bolt", "category": "fact"})
    _call(gm, gm._remember, {"text": "eval: Acme supplies Bolt", "category": "fact"}, scoped=True)
    _, op = _call(gm, gm._list_memories, {})
    _, ev = _call(gm, gm._list_memories, {}, scoped=True)
    texts = lambda r: json.dumps(r)  # noqa: E731
    assert "operator:" in texts(op) and "eval:" not in texts(op)
    assert "eval:" in texts(ev) and "operator:" not in texts(ev)


def test_scoped_forget_cannot_delete_an_operator_memory(gm):
    _call(gm, gm._remember, {"text": "operator memory", "category": "fact"})
    op_id = next(r["id"] for r in _rows(gm, gm._memory_table) if r["user_id"] == "default")
    _call(gm, gm._forget, {"id": op_id}, scoped=True)
    assert any(r["id"] == op_id for r in _rows(gm, gm._memory_table))


def test_filter_injection_is_refused_and_deletes_nothing(gm):
    for t in ("one", "two"):
        _call(gm, gm._remember, {"text": t, "category": "fact"})
    n = len(_rows(gm, gm._memory_table))
    status, body = _call(gm, gm._forget, {"id": "x' OR '1'='1"})
    assert status == 400 and len(_rows(gm, gm._memory_table)) == n
    status, _ = _call(gm, gm._recall, {"query": "one", "category": "fact' OR '1'='1"})
    assert status == 400


def test_forget_scope_needs_a_scope_and_removes_only_the_run(gm):
    _call(gm, gm._remember, {"text": "operator: Acme supplies Bolt", "category": "fact"})
    _call(gm, gm._remember, {"text": "eval: Acme supplies Bolt", "category": "fact"}, scoped=True)
    for table in (gm._memory_table, gm._entities, gm._relations):  # not vacuous: the run has rows
        assert RUN in {r["user_id"] for r in _rows(gm, table)}, table.__name__
    status, _ = _call(gm, gm._forget_scope, {})
    assert status == 400
    status, body = _call(gm, gm._forget_scope, {}, scoped=True)
    assert status == 200 and body["user_id"] == RUN
    for table in (gm._memory_table, gm._entities, gm._relations):
        users = {r["user_id"] for r in _rows(gm, table)}
        assert RUN not in users and (
            users == {"default"} or table is gm._memory_table and users == {"default"}
        )


def test_graph_expansion_never_crosses_users(gm):
    _call(gm, gm._remember, {"text": "operator: Acme supplies Bolt", "category": "fact"})
    _, op = _call(gm, gm._recall, {"query": "Acme", "hops": 2})
    assert "supplies" in json.dumps(op), "not vacuous: the operator's graph expands"
    _, ev = _call(gm, gm._recall, {"query": "Acme", "hops": 2}, scoped=True)
    assert "operator" not in json.dumps(ev) and "supplies" not in json.dumps(ev)


def test_a_run_sees_its_own_graph(gm):
    """Isolation is not just a broken scoped graph: the run expands its own relations."""
    _call(gm, gm._remember, {"text": "eval: Acme supplies Bolt", "category": "fact"}, scoped=True)
    _, ev = _call(gm, gm._recall, {"query": "Acme", "hops": 2}, scoped=True)
    assert "supplies" in json.dumps(ev)
    _, op = _call(gm, gm._recall, {"query": "Acme", "hops": 2})
    assert "supplies" not in json.dumps(op)
