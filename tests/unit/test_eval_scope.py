"""WFE evaluation scope (root-fix Part 2a): the shared scope, the pipeline gate, the registry's
forwarding and the documents MCP's confinement."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi import HTTPException

from portal.platform.mcp_host import eval_scope as es

CAMP = "wfe_" + "a" * 16
RUN = "wfe_" + "b" * 40
SCOPE = {"campaign": CAMP, "run": RUN, "allow": ["create_word_document"]}


@pytest.fixture(autouse=True)
def _no_scope_leaks():
    """Every test starts and must end with no evaluation scope set in this context."""
    assert es.EVAL_SCOPE.get() is None
    assert es.REQUEST_ID.get() == ""
    yield
    leaked = es.EVAL_SCOPE.get()
    leaked_request_id = es.REQUEST_ID.get()
    es.EVAL_SCOPE.set(None)
    es.REQUEST_ID.set("")
    assert leaked is None, "a test left an evaluation scope set"
    assert leaked_request_id == "", "a test left a request id set"


@pytest.mark.parametrize(
    "raw",
    [
        {"campaign": "x", "run": RUN, "allow": ["t"]},
        {"campaign": CAMP, "run": "../etc", "allow": ["t"]},
        {"campaign": CAMP, "run": RUN, "allow": "x"},
        "str",
    ],
)
def test_malformed_scopes_are_refused(raw):
    with pytest.raises(es.ScopeError):
        es.parse(raw)


def test_native_mcp_call_binds_eval_scope_and_request_id():
    from types import SimpleNamespace

    class NativeServer:
        async def call_tool(self, name, arguments, context):
            return es.EVAL_SCOPE.get(), es.REQUEST_ID.get()

    server = NativeServer()
    es.bind_native_context(server)
    context = SimpleNamespace(
        request_context=SimpleNamespace(
            params={
                "_meta": {
                    es.EVAL_META_KEY: SCOPE,
                    es.REQUEST_ID_META_KEY: "chat-17",
                }
            }
        )
    )
    assert asyncio.run(server.call_tool("tool", {}, context)) == (SCOPE, "chat-17")
    assert es.EVAL_SCOPE.get() is None and es.REQUEST_ID.get() == ""


def test_paths_are_confined_to_the_run_root(tmp_path):
    root = es.run_root(tmp_path, SCOPE)
    assert es.confine(tmp_path, SCOPE, "a.docx", sub="in") == root / "in" / "a.docx"
    for bad in ("../../x", "/etc/passwd", str(tmp_path / "other.txt")):
        with pytest.raises(es.ScopeError):
            es.confine(tmp_path, SCOPE, bad)
    (tmp_path / "secret").write_text("s")
    os.symlink(tmp_path / "secret", root / "link")
    with pytest.raises(es.ScopeError):
        es.confine(tmp_path, SCOPE, "link")


def test_receipt_records_the_created_file(tmp_path):
    f = es.run_root(tmp_path, SCOPE) / "out" / "r.docx"
    f.parent.mkdir()
    f.write_bytes(b"doc")
    rec = es.receipt(tmp_path, SCOPE, "Document", f)
    line = json.loads((es.run_root(tmp_path, SCOPE) / ".receipts.jsonl").read_text())
    assert rec == line and rec["size"] == 3 and rec["path"] == str(f.resolve())


def test_pipeline_gate_narrows_tools_and_refuses_a_bad_scope():
    import contextvars

    from portal.platform.inference.router.eval_gate import apply_eval_scope

    assert apply_eval_scope({}, ["a", "b"]) == ["a", "b"]
    body = {"portal_eval": {**SCOPE, "allow": ["b", "zzz"]}}
    ctx = contextvars.copy_context()  # a request's own context, as the ASGI server gives it
    assert ctx.run(apply_eval_scope, body, ["a", "b"]) == ["b"] and "portal_eval" not in body
    assert ctx.run(es.EVAL_SCOPE.get)["run"] == RUN and es.EVAL_SCOPE.get() is None
    with pytest.raises(HTTPException) as e:
        apply_eval_scope({"portal_eval": {"campaign": "bad"}}, ["a"])
    assert e.value.status_code == 400


def test_registry_forwards_the_scope_to_the_mcp(monkeypatch):
    from portal.platform.inference import tool_registry as tr

    seen = {}

    async def fake_call_tool(client, base_url, name, arguments, timeout_s, metadata=None):
        seen["name"], seen["arguments"], seen["metadata"] = name, arguments, metadata
        return {"content": [{"type": "text", "text": '{"ok": true}'}]}

    reg = tr.ToolRegistry()
    tool = type(
        "T",
        (),
        {
            "name": "create_word_document",
            "healthy": True,
            "next_retry_at": 0.0,
            "custom_timeout_s": None,
            "server_id": "documents",
            "server_url": "http://mcp",
            "consecutive_failures": 0,
            "output_schema": None,
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    )()
    monkeypatch.setattr(reg, "get", lambda name: tool)
    monkeypatch.setattr(tr, "call_tool", fake_call_tool)

    async def go():
        token = es.EVAL_SCOPE.set(SCOPE)
        try:
            return await reg.dispatch("create_word_document", {"title": "t"}, request_id="r1")
        finally:
            es.EVAL_SCOPE.reset(token)

    assert asyncio.run(go()) == {"ok": True}
    assert seen["name"] == "create_word_document"
    assert seen["arguments"] == {"title": "t"}
    assert seen["metadata"] == {es.EVAL_META_KEY: SCOPE, es.REQUEST_ID_META_KEY: "r1"}


@pytest.fixture
def docs(tmp_path, monkeypatch):
    from portal.modules.documents.tools import document_mcp as dm

    monkeypatch.setattr(dm, "OUTPUT_DIR", tmp_path)

    def no_publish(*a, **k):
        raise AssertionError("published under an evaluation scope")

    return dm, tmp_path, no_publish


def _invoke(dm, name, body):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/tools/{name}",
            "headers": [],
            "path_params": {"tool_name": name},
        },
        receive,
    )
    resp = asyncio.run(dm.invoke_tool(req))
    return resp.status_code, json.loads(resp.body)


def _route(handler, body):
    from starlette.requests import Request

    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}

    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
    resp = asyncio.run(handler(req))
    return resp.status_code, json.loads(resp.body)


def test_documents_mcp_dispatches_only_manifest_tools(docs):
    dm, _, _ = docs
    status, body = _invoke(dm, "_unique_path", {"arguments": {"name": "x", "ext": "y"}})
    assert status == 404 and "Unknown tool" in body["error"]


def test_documents_mcp_scoped_create_stays_in_the_namespace(docs, monkeypatch):
    pytest.importorskip("docx", reason="python-docx not installed")
    dm, root, no_publish = docs
    monkeypatch.setattr(dm, "publish_file_sync", no_publish)
    status, body = _invoke(
        dm, "create_word_document", {"arguments": {"title": "R", "content": "# H"}, "eval": SCOPE}
    )
    out = es.run_root(root, SCOPE) / "out"
    assert status == 200 and body["success"] and body["receipt"]["sha256"]
    assert "path" not in body
    assert [p.name for p in out.iterdir()] == [os.path.basename(body["receipt"]["path"])]
    assert [p.name for p in root.iterdir()] == ["wfe"]


def test_documents_mcp_scoped_read_outside_the_namespace_is_refused(docs):
    pytest.importorskip("docx", reason="python-docx not installed")
    dm, root, _ = docs
    (root / "operator.docx").write_bytes(b"x")
    status, body = _invoke(
        dm,
        "read_word_document",
        {"arguments": {"file_path": str(root / "operator.docx")}, "eval": SCOPE},
    )
    assert status == 403 and "outside the evaluation namespace" in body["error"]


@pytest.fixture
def data(tmp_path, monkeypatch):
    pytest.importorskip("duckdb", reason="duckdb not installed")
    from portal.modules.data.tools import data_mcp as dm

    root, sess = tmp_path / "ai", tmp_path / "sess"
    root.mkdir()
    monkeypatch.setattr(dm, "_ROOT", root.resolve())
    monkeypatch.setattr(dm, "_SESS_DIR", sess)
    dm._conns.clear()
    yield dm, root, sess
    for c in list(dm._conns.values()):
        c.close()
    dm._conns.clear()


def _scoped(fn, **kwargs):
    token = es.EVAL_SCOPE.set(SCOPE)
    try:
        return fn(**kwargs)
    finally:
        es.EVAL_SCOPE.reset(token)


def test_data_scope_owns_the_session_and_confines_attach(data):
    dm, root, sess = data
    fx = es.run_root(root, SCOPE) / "in"
    fx.mkdir()
    (fx / "sales.csv").write_text("region,amount\neast,10\nwest,5\n")
    body = _scoped(dm.attach_source, session_id="someone_else", path="sales.csv", table="sales")
    assert body["session_id"] == RUN and body["rows"] == 2
    assert (sess / f"{RUN}.duckdb").exists() and not (sess / "someone_else.duckdb").exists()
    body = _scoped(dm.run_sql, session_id="ignored", sql="SELECT sum(amount) AS t FROM sales")
    assert body["session_id"] == RUN and json.dumps(body).count("15") >= 1
    body = _scoped(dm.list_session, session_id="other")
    assert body["session_id"] == RUN and "sales" in body["tables"]
    assert not (sess / "other.duckdb").exists()
    (root / "operator.csv").write_text("a\n1\n")
    body = _scoped(dm.attach_source, session_id="x", path=str(root / "operator.csv"), table="t")
    assert "outside the evaluation namespace" in body.get("error", "")


def test_close_session_is_scope_only_and_deletes_only_that_session(data):
    dm, root, sess = data
    (root / "f.csv").write_text("a\n1\n")
    op = {"session_id": "operator", "path": "f.csv", "table": "t"}
    assert dm.attach_source(**op)["rows"] == 1
    fx = es.run_root(root, SCOPE) / "in"
    fx.mkdir()
    (fx / "f.csv").write_text("a\n1\n")
    _scoped(dm.attach_source, **{**op, "session_id": RUN})
    assert dm.close_session("operator")["error"] == (
        "close_session is available only under an evaluation scope"
    )
    status, body = _route(dm.eval_close_session, {})
    assert status == 400 and "required" in body["error"]
    status, body = _route(dm.eval_close_session, {"eval": SCOPE})
    assert body["closed"] == RUN and f"{RUN}.duckdb" in body["deleted"]
    assert (sess / "operator.duckdb").exists() and not (sess / f"{RUN}.duckdb").exists()
    names = [tool.name for tool in asyncio.run(dm.mcp.list_tools())]
    assert "close_session" not in names


def test_an_empty_allowlist_is_a_sandbox_scope():
    assert es.parse({"campaign": CAMP, "run": RUN, "allow": []})["allow"] == []


def test_the_handler_binds_the_scope_before_injection():
    import contextvars

    from portal.platform.inference.router.eval_gate import bind_eval_scope

    body = {"portal_eval": {**SCOPE, "allow": []}}
    ctx = contextvars.copy_context()
    ctx.run(bind_eval_scope, body)
    assert ctx.run(es.EVAL_SCOPE.get)["run"] == RUN and "portal_eval" in body
    with pytest.raises(HTTPException):
        contextvars.copy_context().run(bind_eval_scope, {"portal_eval": {"campaign": "x"}})


def test_the_trace_records_the_tools_each_request_was_offered(monkeypatch):
    """Live acceptance reads production's own trace: the gate notes what was offered."""
    import contextvars

    from portal.platform.inference.router import eval_gate

    notes = []
    monkeypatch.setattr(eval_gate, "trace_note", lambda **k: notes.append(k))
    ctx = contextvars.copy_context()
    ctx.run(eval_gate.apply_eval_scope, {"portal_eval": {**SCOPE, "allow": ["b"]}}, ["a", "b"])
    contextvars.copy_context().run(eval_gate.apply_eval_scope, {}, ["a", "b"])
    offered = [n["tools_offered"] for n in notes if "tools_offered" in n]
    assert offered == [["b"], ["a", "b"]] and any("eval" in n for n in notes)
