from __future__ import annotations

import io

import pytest


def test_create_powerpoint_writes_native_bullets(tmp_path, monkeypatch) -> None:
    pytest.importorskip("pptx", reason="python-pptx not installed")

    from pptx import Presentation
    from pptx.oxml.ns import qn

    from portal.modules.documents.tools import document_mcp
    from tests.qat.uat_behavioral import validate_pptx_content

    output_path = tmp_path / "uat-bullets.pptx"
    monkeypatch.setattr(document_mcp, "_unique_path", lambda _title, _ext: output_path)
    monkeypatch.setattr(document_mcp, "_published", lambda _path, _noun: {"success": True})

    result = document_mcp.create_powerpoint(
        "UAT presentation",
        [{"title": "Content", "content": "- UAT-PPTX-51\n* second item\n• third item"}],
    )

    assert result["success"] is True
    data = output_path.read_bytes()
    assert validate_pptx_content(data, "UAT-PPTX-51") is None

    presentation = Presentation(io.BytesIO(data))
    paragraphs = presentation.slides[1].placeholders[1].text_frame.paragraphs
    assert [paragraph.text for paragraph in paragraphs] == [
        "UAT-PPTX-51",
        "second item",
        "third item",
    ]
    for paragraph in paragraphs:
        p_pr = paragraph._p.find(qn("a:pPr"))
        assert paragraph.level == 0
        assert p_pr is not None
        assert p_pr.find(qn("a:buNone")) is None
        bullet = p_pr.find(qn("a:buChar"))
        assert bullet is not None and bullet.get("char") == "•"
