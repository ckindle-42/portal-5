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


@pytest.mark.parametrize(
    "raw",
    [
        {"campaign": "x", "run": RUN, "allow": ["t"]},
        {"campaign": CAMP, "run": "../etc", "allow": ["t"]},
        {"campaign": CAMP, "run": RUN, "allow": []},
        "str",
    ],
)
def test_malformed_scopes_are_refused(raw):
    with pytest.raises(es.ScopeError):
        es.parse(raw)


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
    from portal.platform.inference.router.eval_gate import apply_eval_scope

    assert apply_eval_scope({}, ["a", "b"]) == ["a", "b"]
    body = {"portal_eval": {**SCOPE, "allow": ["b", "zzz"]}}
    assert apply_eval_scope(body, ["a", "b"]) == ["b"] and "portal_eval" not in body
    assert es.EVAL_SCOPE.get()["run"] == RUN
    with pytest.raises(HTTPException) as e:
        apply_eval_scope({"portal_eval": {"campaign": "bad"}}, ["a"])
    assert e.value.status_code == 400


def test_registry_forwards_the_scope_to_the_mcp(monkeypatch):
    from portal.platform.inference import tool_registry as tr

    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    class Client:
        async def post(self, url, json=None, timeout=None):
            seen["url"], seen["json"] = url, json
            return Resp()

    reg = tr.ToolRegistry() if hasattr(tr, "ToolRegistry") else type(tr.tool_registry)()
    tool = type(
        "T",
        (),
        {
            "healthy": True,
            "next_retry_at": 0.0,
            "custom_timeout_s": None,
            "server_url": "http://mcp",
            "consecutive_failures": 0,
        },
    )()
    monkeypatch.setattr(reg, "get", lambda name: tool)

    async def client():
        return Client()

    monkeypatch.setattr(reg, "_client", client)

    async def go():
        token = es.EVAL_SCOPE.set(SCOPE)
        try:
            return await reg.dispatch("create_word_document", {"title": "t"}, request_id="r1")
        finally:
            es.EVAL_SCOPE.reset(token)

    assert asyncio.run(go()) == {"ok": True}
    assert seen["json"] == {"arguments": {"title": "t"}, "request_id": "r1", "eval": SCOPE}


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


def test_documents_mcp_dispatches_only_manifest_tools(docs):
    dm, _, _ = docs
    status, body = _invoke(dm, "_unique_path", {"arguments": {"name": "x", "ext": "y"}})
    assert status == 404 and "Unknown tool" in body["error"]


def test_documents_mcp_scoped_create_stays_in_the_namespace(docs, monkeypatch):
    dm, root, no_publish = docs
    monkeypatch.setattr(dm, "publish_file_sync", no_publish)
    status, body = _invoke(
        dm, "create_word_document", {"arguments": {"title": "R", "content": "# H"}, "eval": SCOPE}
    )
    out = es.run_root(root, SCOPE) / "out"
    assert status == 200 and body["success"] and body["receipt"]["sha256"]
    assert [p.name for p in out.iterdir()] == [os.path.basename(body["path"])]
    assert [p.name for p in root.iterdir()] == ["wfe"]


def test_documents_mcp_scoped_read_outside_the_namespace_is_refused(docs):
    dm, root, _ = docs
    (root / "operator.docx").write_bytes(b"x")
    status, body = _invoke(
        dm,
        "read_word_document",
        {"arguments": {"file_path": str(root / "operator.docx")}, "eval": SCOPE},
    )
    assert status == 403 and "outside the evaluation namespace" in body["error"]
