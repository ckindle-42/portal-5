"""Unit tests for portal_mcp.rag.rag_mcp — Docling-enhanced _read_file + LanceDB tools.

All tests mock external deps (Docling, pypdf, python-docx). No network, no real
LanceDB database, and no docling install required: tests patch
rag_mcp._docling_convert and inject fake pypdf/docx modules into sys.modules.
Module import needs lancedb/pyarrow/httpx; tests SKIP gracefully without them
(same pattern as test_mcp_endpoints.py).
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, ".")

rag_mcp = pytest.importorskip(
    "portal_mcp.rag.rag_mcp",
    reason="lancedb/pyarrow/httpx not importable — run: pip install lancedb pyarrow httpx",
)


def _fake_pypdf(text):
    mod = types.ModuleType("pypdf")
    page = MagicMock()
    page.extract_text.return_value = text
    mod.PdfReader = lambda path: MagicMock(pages=[page])
    return mod


def _fake_docx(text):
    mod = types.ModuleType("docx")
    para = MagicMock()
    para.text = text
    mod.Document = lambda path: MagicMock(paragraphs=[para])
    return mod


class TestReadFile:
    """Docling-first _read_file with pypdf/python-docx fallback."""

    def test_read_markdown(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Hello\n\nWorld")
        text = asyncio.run(rag_mcp._read_file(f))
        assert "Hello" in text and "World" in text

    def test_read_text(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("plain text content")
        assert asyncio.run(rag_mcp._read_file(f)) == "plain text content"

    def test_docling_pdf_success(self, tmp_path, monkeypatch):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"dummy")
        monkeypatch.setattr(
            rag_mcp,
            "_docling_convert",
            lambda p: "# Report\n\n| Col1 | Col2 |\n|------|------|\n| A | B |",
        )
        text = asyncio.run(rag_mcp._read_file(f))
        assert "Col1" in text and "Col2" in text

    def test_docling_pptx_supported(self, tmp_path, monkeypatch):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"dummy")
        monkeypatch.setattr(
            rag_mcp, "_docling_convert", lambda p: "# Slide 1\n\nBullet points here"
        )
        assert "Slide 1" in asyncio.run(rag_mcp._read_file(f))

    def test_docling_failure_falls_back_to_pypdf(self, tmp_path, monkeypatch):
        f = tmp_path / "scanned.pdf"
        f.write_bytes(b"dummy")

        def _boom(p):
            raise RuntimeError("no model")

        monkeypatch.setattr(rag_mcp, "_docling_convert", _boom)
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf("fallback text"))
        assert "fallback text" in asyncio.run(rag_mcp._read_file(f))

    def test_docling_short_result_falls_back(self, tmp_path, monkeypatch):
        f = tmp_path / "emptyish.pdf"
        f.write_bytes(b"dummy")
        monkeypatch.setattr(rag_mcp, "_docling_convert", lambda p: "  ")
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf("real content here"))
        assert "real content" in asyncio.run(rag_mcp._read_file(f))

    def test_docling_failure_falls_back_to_docx(self, tmp_path, monkeypatch):
        f = tmp_path / "memo.docx"
        f.write_bytes(b"dummy")

        def _boom(p):
            raise RuntimeError("no model")

        monkeypatch.setattr(rag_mcp, "_docling_convert", _boom)
        monkeypatch.setitem(sys.modules, "docx", _fake_docx("docx fallback paragraph"))
        assert "docx fallback paragraph" in asyncio.run(rag_mcp._read_file(f))

    def test_unsupported_format_returns_empty(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"binary")
        assert asyncio.run(rag_mcp._read_file(f)) == ""


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
