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
import sys
import types
from pathlib import Path
from typing import Any

from portal.platform.inference.router.eval_gate import bind_attached_uploads
from portal.platform.inference.router.preinject import _inject_attached_files
from portal.platform.mcp_host import eval_scope
from portal.platform.mcp_host.workspace import resolve_upload_path

REPO = Path(__file__).resolve().parents[2]

FILTER_SPEC = REPO / "imports" / "openwebui" / "functions" / "portal_attachment_paths.json"


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


def _install_files_stub(monkeypatch: Any, records: dict[str, Any]) -> None:
    """An open_webui.models.files stand-in answering get_file_by_id from ``records``
    (an Exception value raises; a missing id answers None, OWUI's own behaviour)."""
    module = types.ModuleType("open_webui.models.files")

    class _Files:
        async def get_file_by_id(self, fid: str) -> Any:
            record = records.get(fid)
            if isinstance(record, Exception):
                raise record
            return record

    module.Files = _Files()
    monkeypatch.setitem(sys.modules, "open_webui.models.files", module)


def _record(
    fid: str = "ba61aacb-44",
    filename: str = "customers.csv",
    path: str | None = "",
    meta: dict | None = None,
) -> Any:
    return types.SimpleNamespace(
        id=fid,
        filename=filename,
        path=path if path != "" else f"/app/backend/data/uploads/{fid}_customers.csv",
        meta=meta
        if meta is not None
        else {
            "name": filename,
            "content_type": "text/csv",
            "size": 812,
        },
    )


async def _inlet(
    body: dict, monkeypatch: Any = None, records: dict[str, Any] | None = None
) -> dict:
    filter_ = _filter_module().Filter()
    if records is not None:
        _install_files_stub(monkeypatch, records)
    return await filter_.inlet(body)


def test_an_id_only_item_resolves_the_stored_record(monkeypatch) -> None:
    """The defect: OWUI request items often carry {type, id} and nothing else — the
    record, not the item, knows the real name and staged path."""
    out = asyncio.run(
        _inlet(
            {"files": [{"type": "file", "id": "ba61aacb-44"}], "messages": []},
            monkeypatch,
            {"ba61aacb-44": _record()},
        )
    )
    assert out["portal_attached_files"] == [
        {
            "id": "ba61aacb-44",
            "name": "customers.csv",
            "type": "text/csv",
            "size": 812,
            "path": "/workspace/uploads/ba61aacb-44_customers.csv",
        }
    ]


def test_a_richer_ui_item_defers_to_the_record(monkeypatch) -> None:
    out = asyncio.run(
        _inlet(
            {
                "files": [
                    {
                        "id": "ba61aacb-44",
                        "name": "",
                        "type": "file",
                        "meta": {"size": 1},
                    }
                ],
                "messages": [],
            },
            monkeypatch,
            {"ba61aacb-44": _record()},
        )
    )
    assert out["portal_attached_files"] == [
        {
            "id": "ba61aacb-44",
            "name": "customers.csv",
            "type": "text/csv",
            "size": 812,
            "path": "/workspace/uploads/ba61aacb-44_customers.csv",
        }
    ]


def test_a_failed_lookup_falls_back_to_the_item(monkeypatch) -> None:
    body = {"files": [{"type": "file", "id": "ba61aacb-44", "name": "local.csv"}], "messages": []}
    for records in ({"ba61aacb-44": None}, {"ba61aacb-44": RuntimeError("db down")}):
        out = asyncio.run(_inlet(dict(body), monkeypatch, records))
        assert out["portal_attached_files"] == [
            {
                "id": "ba61aacb-44",
                "name": "local.csv",
                "type": "file",
                "size": None,
                "path": "/workspace/uploads/ba61aacb-44_local.csv",
            }
        ]


def test_a_record_without_a_stored_path_keeps_the_staged_name_guess(monkeypatch) -> None:
    out = asyncio.run(
        _inlet(
            {"files": [{"type": "file", "id": "ba61aacb-44"}], "messages": []},
            monkeypatch,
            {"ba61aacb-44": _record(path=None, meta={})},
        )
    )
    assert out["portal_attached_files"] == [
        {
            "id": "ba61aacb-44",
            "name": "customers.csv",
            "type": "file",
            "size": None,
            "path": "/workspace/uploads/ba61aacb-44_customers.csv",
        }
    ]
