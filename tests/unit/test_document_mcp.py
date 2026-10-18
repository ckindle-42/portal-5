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

sys.path.insert(0, ".")

# Guard: skip entire module if portal_mcp.documents is not importable.
pytest.importorskip(
    "portal.modules.documents.tools.document_mcp",
    reason="portal_mcp.documents not importable — run: pip install -e '.[dev,mcp]'",
)


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


class TestReadWordDocument:
    """Tests for read_word_document function."""

    def test_missing_file_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_word_document

        result = read_word_document(str(tmp_path / "nonexistent.docx"))
        assert result["success"] is False
        assert "error" in result

    def test_wrong_extension_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_word_document

        f = tmp_path / "doc.txt"
        f.write_text("hello")
        result = read_word_document(str(f))
        assert result["success"] is False
        assert "error" in result

    def test_valid_docx_returns_success(self, tmp_path):
        """Test with a real .docx if python-docx is installed, skip otherwise."""
        try:
            from docx import Document
        except ImportError:
            pytest.skip("python-docx not installed")

        from portal.modules.documents.tools.document_mcp import read_word_document

        doc = Document()
        doc.add_paragraph("Hello Portal 5")
        path = tmp_path / "test.docx"
        doc.save(str(path))

        result = read_word_document(str(path))
        assert result["success"] is True
        assert result["filename"] == "test.docx"
        assert "content" in result
        assert any("Hello Portal 5" in block["text"] for block in result["content"])

    def test_missing_dep_returns_graceful_error(self, tmp_path, monkeypatch):
        """Simulate python-docx not installed — must return error dict, not raise."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("mocked missing python-docx")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        # Create a valid .docx path so we reach the import check
        f = tmp_path / "doc.docx"
        f.touch()

        from portal.modules.documents.tools import document_mcp

        # Call the raw function to bypass any module-level caching
        result = document_mcp.read_word_document(str(f))
        assert result["success"] is False
        assert "error" in result


class TestReadExcel:
    """Tests for read_excel function."""

    def test_missing_file_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_excel

        result = read_excel(str(tmp_path / "nonexistent.xlsx"))
        assert result["success"] is False
        assert "error" in result

    def test_wrong_extension_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_excel

        f = tmp_path / "file.csv"
        f.write_text("a,b,c")
        result = read_excel(str(f))
        assert result["success"] is False
        assert "error" in result

    def test_valid_xlsx_returns_success(self, tmp_path):
        try:
            import openpyxl
        except ImportError:
            pytest.skip("openpyxl not installed")

        from portal.modules.documents.tools.document_mcp import read_excel

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Name", "Value"])
        ws.append(["Portal5", "42"])
        path = tmp_path / "test.xlsx"
        wb.save(str(path))

        result = read_excel(str(path))
        assert result["success"] is True
        assert result["filename"] == "test.xlsx"
        assert result["sheet_count"] >= 1
        assert "sheets" in result

    def test_max_rows_limits_output(self, tmp_path):
        try:
            import openpyxl
        except ImportError:
            pytest.skip("openpyxl not installed")

        from portal.modules.documents.tools.document_mcp import read_excel

        wb = openpyxl.Workbook()
        ws = wb.active
        for i in range(100):
            ws.append([i, i * 2])
        path = tmp_path / "big.xlsx"
        wb.save(str(path))

        result = read_excel(str(path), max_rows=10)
        assert result["success"] is True
        sheet = result["sheets"][0]
        assert sheet["row_count"] <= 10
        assert sheet["truncated"] is True


class TestReadPowerPoint:
    """Tests for read_powerpoint function."""

    def test_missing_file_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_powerpoint

        result = read_powerpoint(str(tmp_path / "nonexistent.pptx"))
        assert result["success"] is False
        assert "error" in result

    def test_wrong_extension_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_powerpoint

        f = tmp_path / "slides.pdf"
        f.touch()
        result = read_powerpoint(str(f))
        assert result["success"] is False
        assert "error" in result

    def test_valid_pptx_returns_success(self, tmp_path):
        try:
            from pptx import Presentation
        except ImportError:
            pytest.skip("python-pptx not installed")

        from portal.modules.documents.tools.document_mcp import read_powerpoint

        prs = Presentation()
        slide_layout = prs.slide_layouts[0]
        slide = prs.slides.add_slide(slide_layout)
        slide.shapes.title.text = "Test Slide"
        path = tmp_path / "test.pptx"
        prs.save(str(path))

        result = read_powerpoint(str(path))
        assert result["success"] is True
        assert result["filename"] == "test.pptx"
        assert result["slide_count"] >= 1
        assert "slides" in result


class TestReadPDF:
    """Tests for read_pdf function."""

    def test_missing_file_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_pdf

        result = read_pdf(str(tmp_path / "nonexistent.pdf"))
        assert result["success"] is False
        assert "error" in result

    def test_wrong_extension_returns_error(self, tmp_path):
        from portal.modules.documents.tools.document_mcp import read_pdf

        f = tmp_path / "doc.docx"
        f.touch()
        result = read_pdf(str(f))
        assert result["success"] is False
        assert "error" in result

    def test_missing_pdfplumber_returns_graceful_error(self, tmp_path):
        """pdfplumber may not be installed — must return error dict, never raise."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("mocked missing pdfplumber")
            return real_import(name, *args, **kwargs)

        f = tmp_path / "doc.pdf"
        f.touch()

        import unittest.mock as mock

        import portal.modules.documents.tools.document_mcp as doc_mcp

        with mock.patch.dict("sys.modules", {"pdfplumber": None}):
            result = doc_mcp.read_pdf(str(f))
        assert result["success"] is False
        assert "error" in result

    def test_valid_pdf_returns_success(self, tmp_path):
        """Test with a real PDF if pdfplumber is installed, skip otherwise."""
        try:
            import pdfplumber
        except ImportError:
            pytest.skip("pdfplumber not installed")

        # Create a minimal valid PDF using reportlab if available, else skip
        try:
            from reportlab.pdfgen import canvas as rl_canvas
        except ImportError:
            pytest.skip("reportlab not installed (needed to create test PDF)")

        from portal.modules.documents.tools.document_mcp import read_pdf

        path = tmp_path / "test.pdf"
        c = rl_canvas.Canvas(str(path))
        c.drawString(100, 750, "Hello from Portal 5")
        c.save()

        result = read_pdf(str(path))
        assert result["success"] is True
        assert result["filename"] == "test.pdf"
        assert "pages" in result


class TestDocumentCreationOverhaul:
    def test_excel_chart_is_embedded(self, tmp_path, monkeypatch):
        openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

        from portal.modules.documents.tools import document_mcp

        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(
            document_mcp,
            "publish_file_sync",
            lambda path: {"filename": path.name, "url": f"https://example.test/{path.name}"},
        )
        result = document_mcp.create_excel(
            "chart",
            data=[["Region", "Sales"], ["N", 10], ["S", 22]],
            charts=[
                {
                    "type": "bar",
                    "min_col": 2,
                    "max_col": 2,
                    "min_row": 1,
                    "max_row": 3,
                    "cats_col": 1,
                }
            ],
        )
        workbook = openpyxl.load_workbook(result["path"])
        assert result["success"] is True
        assert len(workbook.active._charts) == 1

    def test_rich_markdown_and_template(self, tmp_path, monkeypatch):
        pytest.importorskip("docx", reason="python-docx not installed")
        from docx import Document

        from portal.modules.documents.tools import document_mcp

        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(
            document_mcp,
            "publish_file_sync",
            lambda path: {"filename": path.name, "url": f"https://example.test/{path.name}"},
        )
        result = document_mcp.create_word_document(
            "rich",
            "## Heading\n\n**bold** and `code`\n\n| A | B |\n|---|---|\n| 1 | 2 |",
            template="portal",
        )
        document = Document(result["path"])
        assert result["success"] is True
        assert any(table.cell(1, 1).text == "2" for table in document.tables)
        assert any(run.bold for paragraph in document.paragraphs for run in paragraph.runs)

    def test_export_pdf_reports_missing_libreoffice(self, tmp_path, monkeypatch):
        import subprocess

        from portal.modules.documents.tools import document_mcp

        source = tmp_path / "source.docx"
        source.write_bytes(b"docx")
        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)

        def missing(*args, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", missing)
        result = document_mcp.export_pdf(str(source))
        assert "without LibreOffice" in result["error"]


class TestCreatePowerpointListContent:
    """Models often send slide bullets as a list; that crashed on .splitlines()."""

    def test_list_content_is_joined_not_crashing(self, tmp_path, monkeypatch):
        pytest.importorskip("pptx")
        from portal.modules.documents.tools import document_mcp

        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path, raising=False)
        result = document_mcp.create_powerpoint(
            "Backups",
            [{"title": "Why", "content": ["Recover data", "Meet compliance"]}],
        )
        # publishing needs OWUI_API_KEY (absent in unit tests); the slide build must not crash
        assert "splitlines" not in str(result.get("error", "")), result


class TestReadBareFilename:
    """A bare filename resolves against OUTPUT_DIR and OUTPUT_DIR/uploads."""

    def test_bare_name_in_output_dir_and_uploads(self, tmp_path, monkeypatch):
        from portal.modules.documents.tools import document_mcp

        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)
        (tmp_path / "uploads").mkdir()
        (tmp_path / "a.xlsx").write_bytes(b"x")
        (tmp_path / "uploads" / "1234_b.xlsx").write_bytes(b"x")
        assert document_mcp._resolve_input_path("a.xlsx") == (tmp_path / "a.xlsx").resolve()
        assert (
            document_mcp._resolve_input_path("b.xlsx")
            == (tmp_path / "uploads" / "1234_b.xlsx").resolve()
        )
        assert document_mcp._resolve_input_path("nope.xlsx").name == "nope.xlsx"

    def test_open_webui_file_id_resolves_to_the_stored_upload(self, tmp_path, monkeypatch):
        """OWUI's context names an upload by id (resource-id); it is stored as <id>_<name>."""
        from portal.modules.documents.tools import document_mcp

        monkeypatch.setattr(document_mcp, "OUTPUT_DIR", tmp_path)
        (tmp_path / "uploads").mkdir()
        stored = tmp_path / "uploads" / "ddba5f89-9ad6-438e-a08c-76c3ada6085f_memo.docx"
        stored.write_bytes(b"x")
        got = document_mcp._resolve_input_path("ddba5f89-9ad6-438e-a08c-76c3ada6085f")
        assert got == stored.resolve()
        # a glob metacharacter in the argument matches nothing; it never widens the lookup
        assert document_mcp._resolve_input_path("*").name == "*"


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

    # Each create tool checks for its library before it validates keys, so these
    # skip where CI lacks the optional extras.
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

    def test_accepted_keys_still_create(self, tmp_path, monkeypatch):
        pytest.importorskip("pptx", reason="python-pptx not installed")
        pytest.importorskip("openpyxl", reason="openpyxl not installed")
        m = self._mcp()
        monkeypatch.setattr(m, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(
            m, "publish_file_sync", lambda p: {"filename": p.name, "url": f"https://x/{p.name}"}
        )
        r = m.create_powerpoint(
            "Deck", [{"title": "A", "content": "b", "notes": "n"}, {"title": "B", "content": "c"}]
        )
        assert r["success"] is True
        assert m.create_excel("Book", sheets=[{"name": "A", "headers": ["x"], "rows": [[1]]}])[
            "success"
        ]
