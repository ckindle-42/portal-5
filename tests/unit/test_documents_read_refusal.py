"""N-23: a read outside the readable roots returns the tool's structured error, not an exception."""

from __future__ import annotations

import importlib
import importlib.util

import pytest

dm = importlib.import_module("portal.modules.documents.tools.document_mcp")


@pytest.fixture
def outside(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    monkeypatch.delenv("DOCUMENTS_READ_ROOTS", raising=False)
    secret = tmp_path / "elsewhere" / "data.xlsx"
    secret.parent.mkdir()
    secret.write_bytes(b"not really a workbook")
    return str(secret)


def _needs(module: str):
    """The reader reports its missing library before it checks the path; the dev-only CI extras
    lack these, so the refusal can only be asserted where the library is installed."""
    return pytest.mark.skipif(
        importlib.util.find_spec(module) is None,
        reason=f"{module} is absent (dev-only CI extras)",
    )


@pytest.mark.parametrize(
    "tool",
    [
        pytest.param("read_excel", marks=_needs("openpyxl")),
        pytest.param("read_word_document", marks=_needs("docx")),
        pytest.param("read_powerpoint", marks=_needs("pptx")),
        pytest.param("read_pdf", marks=_needs("pdfplumber")),
    ],
)
def test_a_refused_read_is_a_structured_error(tool, outside):
    out = getattr(dm, tool)(outside)
    assert out["success"] is False
    assert "outside the readable roots" in out["error"]
