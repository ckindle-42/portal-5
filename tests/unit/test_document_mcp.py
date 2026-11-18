"""tests/unit/test_document_mcp.py

Unit tests for document MCP read tools added in commit 57b2f2c:
  - read_word_document
  - read_excel
  - read_powerpoint
  - read_pdf

All tests run without network or Docker. File I/O tests use tmp_path fixtures.
Tests skip gracefully when heavy deps (python-docx, openpyxl, pptx, pdfplumber)
are not installed — consistent with existing MCP test conventions.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _temp_dirs_are_allowed_roots(monkeypatch):
    """These tests read and ingest from temporary directories; allow exactly those (DOCUMENTS_READ_ROOTS).
    Production confines reads and ingest to configured roots (N-23, N-28)."""
    import tempfile

    monkeypatch.setenv("DOCUMENTS_READ_ROOTS", tempfile.gettempdir())


class TestToolsManifest:
    """TOOLS_MANIFEST must include all four new read tools."""

    def test_manifest_includes_read_word_document(self):
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        names = [t["name"] for t in TOOLS_MANIFEST]
        assert "read_word_document" in names, (
            "TOOLS_MANIFEST missing 'read_word_document' — Open WebUI won't expose this tool"
        )

    def test_manifest_includes_read_excel(self):
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        names = [t["name"] for t in TOOLS_MANIFEST]
        assert "read_excel" in names, "TOOLS_MANIFEST missing 'read_excel'"

    def test_manifest_includes_read_powerpoint(self):
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        names = [t["name"] for t in TOOLS_MANIFEST]
        assert "read_powerpoint" in names, "TOOLS_MANIFEST missing 'read_powerpoint'"

    def test_manifest_includes_read_pdf(self):
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        names = [t["name"] for t in TOOLS_MANIFEST]
        assert "read_pdf" in names, "TOOLS_MANIFEST missing 'read_pdf'"

    def test_manifest_total_count(self):
        """Manifest must have at least 9 tools (5 original + 4 read tools)."""
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        assert len(TOOLS_MANIFEST) >= 9, (
            f"Expected at least 9 tools in TOOLS_MANIFEST, got {len(TOOLS_MANIFEST)}"
        )

    def test_read_tools_have_file_path_parameter(self):
        """All read tools must declare file_path as a required parameter."""
        from portal.modules.documents.tools.document_mcp import TOOLS_MANIFEST

        read_tools = [t for t in TOOLS_MANIFEST if t["name"].startswith("read_")]
        assert len(read_tools) == 4, f"Expected 4 read_ tools, got {len(read_tools)}"
        for tool in read_tools:
            props = tool.get("parameters", {}).get("properties", {})
            assert "file_path" in props, f"Tool '{tool['name']}' missing 'file_path' in parameters"


def test_word_document_tool_says_how_to_express_a_table():
    """A model can only build a table if the tool tells it markdown pipe rows make one."""
    from portal.modules.documents.tools import document_mcp

    manifest = {t["name"]: t for t in document_mcp.TOOLS_MANIFEST}
    desc = manifest["create_word_document"]["parameters"]["properties"]["content"]["description"]
    assert "table" in desc and "|---|" in desc
    assert "table" in (document_mcp.create_word_document.__doc__ or "")


def test_every_required_manifest_parameter_is_defined_and_real():
    """create_excel once required `title` without defining it: the model was never told the name."""
    import inspect

    from portal.modules.documents.tools import document_mcp

    for tool in document_mcp.TOOLS_MANIFEST:
        props, req = (
            tool["parameters"].get("properties", {}),
            tool["parameters"].get("required", []),
        )
        assert set(req) <= set(props), (tool["name"], sorted(set(req) - set(props)))
        params = inspect.signature(getattr(document_mcp, tool["name"])).parameters
        assert set(props) <= set(params), (tool["name"], sorted(set(props) - set(params)))
        needed = {n for n, p in params.items() if p.default is inspect.Parameter.empty}
        assert needed <= set(req), (tool["name"], sorted(needed - set(req)))


def test_powerpoint_slides_schema_names_the_keys_the_tool_reads():
    """Qwen sent {"title", "text"} and the tool silently dropped the bodies: the keys were never stated."""
    from portal.modules.documents.tools import document_mcp

    tool = next(t for t in document_mcp.TOOLS_MANIFEST if t["name"] == "create_powerpoint")
    slides = tool["parameters"]["properties"]["slides"]
    assert {"title", "content", "notes"} <= set(slides["items"]["properties"])
    assert "content" in slides["description"]


def test_auto_documents_prompt_names_the_read_parameter():
    """'pass the file name' led the seat to send file_name/file; the parameter is file_path."""
    from pathlib import Path

    import yaml

    ws = yaml.safe_load(Path("config/portal.yaml").read_text())["workspaces"]["auto-documents"]
    assert "file_path" in ws["owui_system_prompt"]


class TestCreateToolsRejectKeysTheyWouldDrop:
    """A create tool that ignores a key and reports success makes the model tell the user it wrote
    content that is not in the file (Qwen sent {"title", "text"} to create_powerpoint)."""

    def _mcp(self):
        from portal.modules.documents.tools import document_mcp

        return document_mcp

    def test_powerpoint_slide_with_text_instead_of_content(self):
        pytest.importorskip("pptx", reason="python-pptx not installed")
        r = self._mcp().create_powerpoint(
            "Deck", [{"title": "Yields", "text": "Up twelve percent"}]
        )
        assert r["success"] is False
        assert "'text'" in r["error"] and "title, content, notes" in r["error"]

    def test_powerpoint_nested_chart_and_image_keys(self):
        pytest.importorskip("pptx", reason="python-pptx not installed")
        m = self._mcp()
        bad_chart = m.create_powerpoint("D", [{"title": "t", "chart": {"kind": "bar"}}])
        assert not bad_chart["success"] and "chart of slide 1" in bad_chart["error"]
        bad_img = m.create_powerpoint("D", [{"title": "t", "images": [{"url": "x"}]}])
        assert not bad_img["success"] and "image of slide 1" in bad_img["error"]

    def test_excel_sheet_with_columns_instead_of_headers(self):
        pytest.importorskip("openpyxl", reason="openpyxl not installed")
        r = self._mcp().create_excel("Book", sheets=[{"name": "A", "columns": ["x"], "rows": []}])
        assert (
            r["success"] is False
            and "'columns'" in r["error"]
            and "name, headers, rows" in r["error"]
        )

    def test_excel_nested_header_row_is_a_structured_error(self):
        pytest.importorskip("openpyxl", reason="openpyxl not installed")
        r = self._mcp().create_excel(
            "Book", sheets=[{"name": "A", "headers": [["x", "y"]], "rows": [["1", "2"]]}]
        )
        assert r["success"] is False and "headers of sheet 1" in r["error"]
        assert "flat list" in r["error"]

    def test_excel_flat_rows_still_succeed_validation(self):
        m = self._mcp()
        assert m._non_scalar_cell([["a", 1], ["b", 2.5]], "row") is None
        assert m._non_scalar_cell([["a", ["b"]]], "row")["success"] is False

    def test_excel_chart_unknown_key(self):
        pytest.importorskip("openpyxl", reason="openpyxl not installed")
        r = self._mcp().create_excel("B", data=[["a"]], charts=[{"type": "bar", "colour": "red"}])
        assert r["success"] is False and "'colour'" in r["error"]

    def test_word_image_unknown_key(self):
        pytest.importorskip("docx", reason="python-docx not installed")
        r = self._mcp().create_word_document("D", "text", images=[{"url": "x"}])
        assert r["success"] is False and "'url'" in r["error"] and "source" in r["error"]

    def test_non_object_items_are_a_structured_error(self):
        pytest.importorskip("pptx", reason="python-pptx not installed")
        assert not self._mcp().create_powerpoint("D", ["just a string"])["success"]
