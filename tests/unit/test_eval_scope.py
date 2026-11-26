"""WFE evaluation scope (root-fix Part 2a): the shared scope, the pipeline gate, the registry's
forwarding and the documents MCP's confinement."""

from __future__ import annotations

import asyncio
import json

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
    assert es.WORKSPACE_ID.get() == ""
    yield
    leaked = es.EVAL_SCOPE.get()
    leaked_request_id = es.REQUEST_ID.get()
    leaked_workspace_id = es.WORKSPACE_ID.get()
    es.EVAL_SCOPE.set(None)
    es.REQUEST_ID.set("")
    es.WORKSPACE_ID.set("")
    assert leaked is None, "a test left an evaluation scope set"
    assert leaked_request_id == "", "a test left a request id set"
    assert leaked_workspace_id == "", "a test left a workspace id set"


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


def test_native_mcp_call_binds_pipeline_workspace_id():
    from types import SimpleNamespace

    class NativeServer:
        async def call_tool(self, name, arguments, context):
            return es.WORKSPACE_ID.get()

    server = NativeServer()
    es.bind_native_context(server)
    context = SimpleNamespace(
        request_context=SimpleNamespace(
            params={"_meta": {es.WORKSPACE_ID_META_KEY: "auto-security::purpleteam-exec"}}
        )
    )
    assert asyncio.run(server.call_tool("execute_bash", {}, context)) == (
        "auto-security::purpleteam-exec"
    )
    assert es.WORKSPACE_ID.get() == ""


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


def test_documents_mcp_scoped_read_outside_the_namespace_is_refused(docs):
    """REST used to answer 403 because ScopeError escaped the tool. The read now
    catches it as PermissionError and returns the same structured refusal the
    native path returns, so a later corrected path is not a tool-error backoff."""
    pytest.importorskip("docx", reason="python-docx not installed")
    dm, root, _ = docs
    (root / "operator.docx").write_bytes(b"x")
    status, body = _invoke(
        dm,
        "read_word_document",
        {"arguments": {"file_path": str(root / "operator.docx")}, "eval": SCOPE},
    )
    assert status == 200 and body["success"] is False
    assert "outside the evaluation namespace" in body["error"]


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


def test_upload_ids_are_strings_deduplicated_and_capped():
    from portal.platform.mcp_host import eval_scope

    assert eval_scope.upload_ids(None) == ()
    assert eval_scope.upload_ids("file-id") == ()
    assert eval_scope.upload_ids(["a", "", 3, "a", " b "]) == ("a", "b")
    many = [f"id{i}" for i in range(100)]
    assert len(eval_scope.upload_ids(many)) == eval_scope.MAX_ATTACHED_UPLOADS


def test_pipeline_binds_the_requests_owui_attachments():
    from portal.platform.inference.router.eval_gate import bind_attached_uploads
    from portal.platform.mcp_host import eval_scope

    token = eval_scope.ATTACHED_UPLOADS.set(())
    try:
        bind_attached_uploads({"files": [{"id": "f1", "name": "a.csv"}, {"name": "no-id"}, "x"]})
        assert eval_scope.ATTACHED_UPLOADS.get() == ("f1",)
        bind_attached_uploads({"messages": []})
        assert eval_scope.ATTACHED_UPLOADS.get() == ()
    finally:
        eval_scope.ATTACHED_UPLOADS.reset(token)


def test_native_mcp_call_binds_attached_uploads():
    from types import SimpleNamespace

    class NativeServer:
        async def call_tool(self, name, arguments, context):
            return es.ATTACHED_UPLOADS.get()

    server = NativeServer()
    es.bind_native_context(server)
    context = SimpleNamespace(
        request_context=SimpleNamespace(params={"_meta": {es.UPLOADS_META_KEY: ["f1", "f2"]}})
    )
    assert asyncio.run(server.call_tool("execute_python", {}, context)) == ("f1", "f2")
    assert es.ATTACHED_UPLOADS.get() == ()
