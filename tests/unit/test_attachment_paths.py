"""The OWUI attachment-path defect fix: filter field forwarding, pipeline notes, seeding.

Production chat: OWUI's portal_attachment_paths inlet filter carries each attachment
{id, name, type, size, path} on body["portal_attached_files"]; OWUI pops body["files"]
(v0.12.5 middleware.py process_chat_payload) and metadata (routers/openai.py
generate_chat_completion) before the pipeline hop, so the custom top-level key is what
a live chat arrives with. The pipeline notes each file with its sandbox path; the eval
scope binds the same ids.
"""

from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path
from typing import Any

from portal.platform.inference.router.eval_gate import bind_attached_uploads
from portal.platform.inference.router.preinject import _inject_attached_files
from portal.platform.mcp_host import eval_scope
from portal.platform.mcp_host.workspace import resolve_upload_path

REPO = Path(__file__).resolve().parents[2]
FILTER_SPEC = REPO / "imports" / "openwebui" / "functions" / "portal_attachment_paths.json"
RAG_SEED = REPO / "imports" / "openwebui" / "rag_template.txt"


# --- Pipeline note from the forwarded field -----------------------------------


def _body(attachments: list[dict]) -> dict[str, Any]:
    return {
        "model": "auto-daily",
        "messages": [{"role": "user", "content": "sum the totals"}],
        "portal_attached_files": attachments,
    }


def test_note_from_the_forwarded_field_names_the_path() -> None:
    out = _inject_attached_files(
        _body(
            [
                {
                    "id": "ba61aacb-4f",
                    "name": "customers.csv",
                    "type": "file",
                    "size": 812,
                    "path": "/workspace/uploads/ba61aacb-4f_customers.csv",
                }
            ]
        )
    )
    text = out["messages"][-1]["content"]
    assert text.startswith("sum the totals")
    assert (
        "[Attached file — id: 'ba61aacb-4f', name: 'customers.csv', type: 'file', "
        "path: '/workspace/uploads/ba61aacb-4f_customers.csv']" in text
    )


def test_files_items_keep_the_pathless_note() -> None:
    out = _inject_attached_files(
        {
            "messages": [{"role": "user", "content": "q"}],
            "files": [{"id": "f1", "name": "a.csv", "type": "file"}],
        }
    )
    assert (
        "[Attached file — id: 'f1', name: 'a.csv', type: 'file']" in out["messages"][-1]["content"]
    )


def test_an_id_present_on_both_fields_is_noted_once() -> None:
    out = _inject_attached_files(
        {
            "messages": [{"role": "user", "content": "q"}],
            "files": [{"id": "f1", "name": "a.csv", "type": "file"}],
            "portal_attached_files": [
                {"id": "f1", "name": "a.csv", "type": "file", "path": "/workspace/uploads/f1_a.csv"}
            ],
        }
    )
    note = out["messages"][-1]["content"]
    assert note.count("Attached file") == 1 and "/workspace/uploads/f1_a.csv" in note


def test_no_attachments_leaves_the_body_alone() -> None:
    body: dict[str, Any] = {"messages": [{"role": "user", "content": "q"}]}
    assert _inject_attached_files(body) == body
    body["portal_attached_files"] = [{"id": "", "name": "", "type": "file"}]
    assert _inject_attached_files(body) == body


# --- Eval scope binding --------------------------------------------------------


def test_bind_attached_uploads_reads_both_fields() -> None:
    token = eval_scope.ATTACHED_UPLOADS.set(())
    try:
        bind_attached_uploads(
            {
                "files": [{"id": "f1", "name": "a.csv"}, {"name": "no-id"}, "x"],
                "portal_attached_files": [
                    {"id": "uuid-1", "name": "b.pdf", "type": "file", "path": "/x"},
                    {"id": "f1", "name": "a.csv", "type": "file", "path": "/y"},
                ],
            }
        )
        assert eval_scope.ATTACHED_UPLOADS.get() == ("f1", "uuid-1")
    finally:
        eval_scope.ATTACHED_UPLOADS.reset(token)


def test_bind_attached_uploads_without_either_field_clears() -> None:
    token = eval_scope.ATTACHED_UPLOADS.set(("stale",))
    try:
        bind_attached_uploads({"messages": []})
        assert eval_scope.ATTACHED_UPLOADS.get() == ()
    finally:
        eval_scope.ATTACHED_UPLOADS.reset(token)


# --- resolve_upload_path consistency -------------------------------------------


def test_nested_attachment_id_resolves_under_uploads(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("AI_OUTPUT_DIR", raising=False)
    uploads = tmp_path / "uploads"
    nested = uploads / "realuse_v1" / "ru-v1-005"
    nested.mkdir(parents=True)
    (nested / "customers.csv").write_text("id,name\n1,a\n")
    assert (
        resolve_upload_path("realuse_v1/ru-v1-005/customers.csv")
        == (nested / "customers.csv").resolve()
    )
    assert resolve_upload_path("realuse_v1/ru-v1-005/missing.csv") is None
    assert resolve_upload_path("../outside.csv") is None


# --- Seeded artifacts ----------------------------------------------------------


def _filter_module() -> Any:
    spec = json.loads(FILTER_SPEC.read_text())
    module = types.ModuleType(spec["id"])
    exec(compile(spec["content"], spec["id"], "exec"), module.__dict__)
    return module


def test_seeded_filter_spec_is_valid() -> None:
    spec = json.loads(FILTER_SPEC.read_text())
    assert spec["id"].isidentifier() and spec["type"] == "filter"
    # No file_handler attribute: that would make OWUI delete the files metadata
    # and kill the RAG retrieval path the Portal template relies on.
    assert "class Filter" in spec["content"] and "file_handler =" not in spec["content"]


def test_filter_inlet_golden() -> None:
    filter_ = _filter_module().Filter()
    out = filter_.inlet(
        {
            "files": [
                {
                    "id": "ba61aacb-44",
                    "name": "report.csv",
                    "type": "file",
                    "meta": {"size": 812},
                },
                {"id": "ba61aacb-44", "name": "report.csv", "type": "file"},
                {"id": "", "name": "no-id", "type": "file"},
                {"collection_name": "kb", "name": "kb", "type": "collection"},
                "junk",
            ],
            "messages": [],
        }
    )
    assert out["portal_attached_files"] == [
        {
            "id": "ba61aacb-44",
            "name": "report.csv",
            "type": "file",
            "size": 812,
            "path": "/workspace/uploads/ba61aacb-44_report.csv",
        }
    ]
    assert filter_.inlet({"messages": []}) == {"messages": []}
    assert filter_.inlet({"files": "not-a-list", "messages": []}) == {
        "files": "not-a-list",
        "messages": [],
    }


def test_rag_seed_file_is_the_harness_portal_template() -> None:
    from tests.wfe.owui_rag import DEFAULT_RAG_TEMPLATE, PORTAL_RAG_GUIDELINE, PORTAL_RAG_TEMPLATE

    assert RAG_SEED.read_text() == PORTAL_RAG_TEMPLATE
    # The delta against stock is exactly the one guideline line.
    assert (
        DEFAULT_RAG_TEMPLATE.replace(
            "- Do not use XML tags in your response.",
            f"{PORTAL_RAG_GUIDELINE}\n- Do not use XML tags in your response.",
        )
        == PORTAL_RAG_TEMPLATE
    )
    assert PORTAL_RAG_TEMPLATE.count("excerpts of attached files") == 1
    assert DEFAULT_RAG_TEMPLATE.count("excerpts of attached files") == 0


# --- openwebui_init seeding calls ----------------------------------------------


class _Resp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload or {})

    def json(self) -> Any:
        return self._payload


class _FakeAsync:
    """Records calls; GET answers from a route table keyed by URL, POST succeeds."""

    def __init__(self, routes: dict[str, _Resp]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, Any]] = []

    async def get(self, url: str, **_kw: Any) -> _Resp:
        self.calls.append(("GET", url, None))
        return self.routes.get(url, _Resp(404))

    async def post(self, url: str, **kw: Any) -> _Resp:
        self.calls.append(("POST", url, kw.get("json")))
        return _Resp(201, kw.get("json"))


class _FakeSync:
    def __init__(self, get_resp: _Resp) -> None:
        self.get_resp = get_resp
        self.calls: list[tuple[str, str, Any]] = []

    def get(self, url: str, **_kw: Any) -> _Resp:
        self.calls.append(("GET", url, None))
        return self.get_resp

    def post(self, url: str, **kw: Any) -> _Resp:
        self.calls.append(("POST", url, kw.get("json")))
        return _Resp(200, kw.get("json"))


def _seeder() -> Any:
    import importlib.util
    import os

    os.environ.setdefault("OPENWEBUI_ADMIN_PASSWORD", "test-not-used")
    spec = importlib.util.spec_from_file_location(
        "openwebui_init_attachment_seed", REPO / "scripts" / "openwebui_init.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The module's defaults are the init container's mount points (/imports, /personas);
    # tests read the repo checkout instead.
    module.IMPORTS_DIR = REPO / "imports" / "openwebui"
    module.FUNCTIONS_DIR = module.IMPORTS_DIR / "functions"
    module.RAG_TEMPLATE_FILE = module.IMPORTS_DIR / "rag_template.txt"
    module.PERSONAS_DIR = REPO / "config" / "personas"
    return module


def test_seed_creates_and_enables_the_filter() -> None:
    seeder = _seeder()
    spec = json.loads(FILTER_SPEC.read_text())
    fid = spec["id"]
    client = _FakeAsync({})
    asyncio.run(seeder.seed_attachment_filter_async(client, "tok"))
    posts = client.calls[1:]  # first call is the GET
    assert client.calls[0] == ("GET", f"{seeder.OPENWEBUI_URL}/api/v1/functions/id/{fid}", None)
    assert [u.split("/api/v1/functions/")[-1] for _, u, _ in posts] == [
        "create",
        f"id/{fid}/toggle",
        f"id/{fid}/toggle/global",
    ]
    created = posts[0][2]
    assert created["id"] == fid and created["content"] == spec["content"]


def test_seed_updates_only_when_content_differs() -> None:
    seeder = _seeder()
    spec = json.loads(FILTER_SPEC.read_text())
    fid = spec["id"]
    url = f"{seeder.OPENWEBUI_URL}/api/v1/functions/id/{fid}"
    stale = {"id": fid, "content": "old source", "is_active": True, "is_global": True}
    client = _FakeAsync({url: _Resp(200, stale)})
    asyncio.run(seeder.seed_attachment_filter_async(client, "tok"))
    endpoints = [u.rsplit("/", 1)[-1] for method, u, _ in client.calls if method == "POST"]
    assert endpoints == ["update"]


def test_seed_skips_a_current_enabled_filter() -> None:
    seeder = _seeder()
    spec = json.loads(FILTER_SPEC.read_text())
    fid = spec["id"]
    url = f"{seeder.OPENWEBUI_URL}/api/v1/functions/id/{fid}"
    current = {"id": fid, "content": spec["content"], "is_active": True, "is_global": True}
    client = _FakeAsync({url: _Resp(200, current)})
    asyncio.run(seeder.seed_attachment_filter_async(client, "tok"))
    assert [c for c in client.calls if c[0] == "POST"] == []


def test_configure_rag_template_posts_only_when_different() -> None:
    seeder = _seeder()
    template = RAG_SEED.read_text()
    current = _FakeSync(_Resp(200, {"RAG_TEMPLATE": template}))
    seeder.configure_rag_template(current, "tok")
    assert [c for c in current.calls if c[0] == "POST"] == []

    stale = _FakeSync(_Resp(200, {"RAG_TEMPLATE": "stock"}))
    seeder.configure_rag_template(stale, "tok")
    posts = [c for c in stale.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1].endswith("/retrieval/config/update")
    assert posts[0][2] == {"RAG_TEMPLATE": template}
