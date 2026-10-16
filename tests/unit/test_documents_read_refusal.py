"""N-23: a read outside the readable roots returns the tool's structured error, not an exception."""

from __future__ import annotations

import importlib

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


@pytest.mark.parametrize(
    "tool", ["read_excel", "read_word_document", "read_powerpoint", "read_pdf"]
)
def test_a_refused_read_is_a_structured_error(tool, outside):
    out = getattr(dm, tool)(outside)
    assert out["success"] is False
    assert "outside the readable roots" in out["error"]
