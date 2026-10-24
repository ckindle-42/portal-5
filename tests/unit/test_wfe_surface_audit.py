"""The surface audit's detectors, on small fixtures: each defect class it exists to find."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import httpx

from portal.platform.inference import tool_registry as registry_module

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "wfe_surface_audit", ROOT / "scripts" / "wfe_surface_audit.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _fn(src: str):
    return ast.parse(src).body[0]


def test_signature_rows_flag_undefined_extra_and_missing_required():
    fn = _fn("def f(file_path, max_rows=5): pass")
    rows = audit.signature_rows("m / f", {"audio_path": {}, "max_rows": {}}, set(), fn)
    kinds = {(r[2], r[3].split(":")[0]) for r in rows}
    assert ("open", "manifest params not in the function") in kinds
    assert ("open", "function requires ['file_path'], manifest does not") in kinds


def test_shape_rows_flag_arrays_and_objects_with_no_keys():
    rows = audit.shape_rows(
        "m / f",
        {
            "slides": {"type": "array", "items": {"type": "object"}},
            "data": {"type": "array"},
            "opts": {"type": "object"},
            "ok": {"type": "array", "items": {"type": "object", "properties": {"a": {}}}},
        },
    )
    assert sorted(r[1] for r in rows) == ["m / f.data", "m / f.opts", "m / f.slides"]


def test_filtering_dispatcher_pattern_matches_the_whisper_shape():
    bad = "filtered = {k: v for k, v in arguments.items() if k in valid}"
    assert audit.FILTERING.search(bad)
    assert not audit.FILTERING.search("unknown = sorted(set(arguments) - valid)")


def test_no_dispatcher_silently_filters_unknown_arguments():
    assert audit.filtering_dispatchers() == []


# ---- class 3: the probe path -----------------------------------------------


def _rpc(request_id: str, result: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json={"jsonrpc": "2.0", "id": request_id, "result": result})


def test_class3_pipeline_rejects_unknown_key_before_the_call(monkeypatch):
    """Default mode probes through ToolRegistry.dispatch: a closed schema rejects the
    extra key before the server is called, an open schema still reports acceptance."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["method"])
        if body["method"] == "tools/list":
            return _rpc(
                body["id"],
                {
                    "tools": [
                        {
                            "name": "list_widgets",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"q": {"type": "string"}},
                                "required": ["q"],
                            },
                        },
                        {
                            "name": "search_open",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"q": {"type": "string"}},
                                "additionalProperties": True,
                            },
                        },
                    ]
                },
            )
        return _rpc(body["id"], {"structuredContent": {"success": True}, "content": []})

    import portal.platform.inference.mcp_http as mcp_http

    mcp_http._SERVER_STATES.clear()
    mcp_http._SERVER_LOCKS.clear()
    monkeypatch.setattr(registry_module, "MCP_SERVERS", {"whisper": "http://whisper.test"})
    real = registry_module.ToolRegistry

    def factory() -> registry_module.ToolRegistry:
        registry = real()
        registry._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return registry

    monkeypatch.setattr(registry_module, "ToolRegistry", factory)
    try:
        rows = [r for r in audit.class3() if r[1].startswith("whisper / ")]
    finally:
        mcp_http._SERVER_STATES.clear()
        mcp_http._SERVER_LOCKS.clear()

    assert (
        "3",
        "whisper / list_widgets",
        "ok",
        "extra key rejected by the pipeline before the call",
    ) in rows
    assert (
        "3",
        "whisper / search_open",
        "open",
        "extra key accepted: success with an unknown argument",
    ) in rows
    assert calls.count("tools/call") == 1  # the closed schema never reached the server


def test_class3_direct_reports_server_behaviour(monkeypatch):
    """--direct calls the MCP itself: a server that silently drops the key stays open."""
    monkeypatch.setattr(
        audit, "load_portal", lambda: {"mcp_fleet": [{"id": "whisper", "port": 8915}]}
    )
    monkeypatch.setattr(
        audit,
        "_listed_tools",
        lambda base: (
            [
                {
                    "name": "list_transcripts",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer"}},
                        "required": ["limit"],
                    },
                }
            ],
            "native",
        ),
    )

    def invoke(base: str, mode: str, name: str, args: dict) -> tuple[str, int]:
        assert args["limit"] == 1 and args["zz_unknown_probe"] == 1
        return json.dumps({"structuredContent": {"success": True}, "content": []}), 200

    monkeypatch.setattr(audit, "_invoke_listed_tool", invoke)
    rows = audit.class3(direct=True)
    assert (
        "3",
        "whisper / list_transcripts",
        "open",
        "extra key accepted: success with an unknown argument",
    ) in rows


def test_manifests_pass_the_integrity_classes_the_audit_closed():
    """required parameters are defined and match the functions, across every MCP manifest."""
    assert [r for r in audit.class2() if r[2] == "open"] == []
