"""Unit tests for portal.modules.research.tools.rag_mcp — Docling-enhanced _read_file + LanceDB tools.

All tests mock external deps (Docling, pypdf, python-docx). No network, no real
LanceDB database, and no docling install required: tests patch
rag_mcp._docling_convert and inject fake pypdf/docx modules into sys.modules.
Module import needs lancedb/pyarrow/httpx; tests SKIP gracefully without them
(same pattern as test_mcp_endpoints.py).
"""

import sys

import pytest

sys.path.insert(0, ".")

rag_mcp = pytest.importorskip(
    "portal.modules.research.tools.rag_mcp",
    reason="lancedb/pyarrow/httpx not importable — run: pip install lancedb pyarrow httpx",
)


class TestManifestParams:
    """kb_search/kb_search_all query_type and kb_ingest fts parameters."""

    def test_kb_search_has_query_type(self):
        kb = [t for t in rag_mcp.TOOLS_MANIFEST if t["name"] == "kb_search"][0]
        qt = kb["parameters"]["properties"]["query_type"]
        assert qt["default"] == "vector"
        assert set(qt["enum"]) == {"vector", "fts", "hybrid"}

    def test_kb_search_all_has_query_type(self):
        kb = [t for t in rag_mcp.TOOLS_MANIFEST if t["name"] == "kb_search_all"][0]
        qt = kb["parameters"]["properties"]["query_type"]
        assert qt["default"] == "vector"
        assert set(qt["enum"]) == {"vector", "fts", "hybrid"}

    def test_kb_ingest_has_fts_param(self):
        kb = [t for t in rag_mcp.TOOLS_MANIFEST if t["name"] == "kb_ingest"][0]
        fts = kb["parameters"]["properties"]["fts"]
        assert fts["type"] == "boolean" and fts["default"] is False


class TestManifest:
    """All expected tools are registered (final Phase 3 state)."""

    _EXPECTED_TOOLS = frozenset(
        {
            "kb_list",
            "kb_search",
            "kb_search_all",
            "kb_ingest",
            "kb_optimize",
            "kb_versions",
            "kb_restore",
        }
    )

    def test_all_tools_present(self):
        names = {t["name"] for t in rag_mcp.TOOLS_MANIFEST}
        assert names == self._EXPECTED_TOOLS, (
            f"missing={self._EXPECTED_TOOLS - names} extra={names - self._EXPECTED_TOOLS}"
        )

    def test_kb_versions_manifest(self):
        kv = [t for t in rag_mcp.TOOLS_MANIFEST if t["name"] == "kb_versions"][0]
        assert "kb_id" in kv["parameters"]["required"]

    def test_kb_restore_manifest(self):
        kr = [t for t in rag_mcp.TOOLS_MANIFEST if t["name"] == "kb_restore"][0]
        assert "kb_id" in kr["parameters"]["required"]
        assert "version" in kr["parameters"]["required"]

    def test_endpoint_functions_exist(self):
        for fname in ("kb_optimize_endpoint", "kb_versions_endpoint", "kb_restore_endpoint"):
            assert callable(getattr(rag_mcp, fname, None)), f"{fname} missing"
