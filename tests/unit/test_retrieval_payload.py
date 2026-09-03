"""T2 P2 — citable locators (O2) and no placeholder-as-content (O3).

O2: text hits must carry `char_start`/`char_end` (stored at ingest) and `page`
(absent, never guessed, until the docling chunker supplies it).
O3: a page-image hit must not present `"[page image f.pdf p3]"` as content; it
is a pointer the model cannot read, and the router must not inject it as
grounding.
"""

from __future__ import annotations

from portal.platform.inference.router import context_inject
from portal.platform.retrieval import fusion


def test_text_payload_carries_locators_and_absent_page():
    row = {
        "chunk_id": "c1",
        "source_file": "cip-007.pdf",
        "chunk_index": 3,
        "text": "Patch evaluation within 35 calendar days.",
        "char_start": 1200,
        "char_end": 1240,
    }
    p = fusion._text_payload(row)
    assert p["kind"] == "text" and p["content_available"] is True
    assert p["char_start"] == 1200 and p["char_end"] == 1240
    assert p["page"] is None  # not fabricated — the chunker doesn't supply it yet
    assert p["text"] == row["text"]


def test_text_payload_uses_page_when_the_chunker_supplies_it():
    row = {
        "chunk_id": "c2",
        "source_file": "f.pdf",
        "chunk_index": 0,
        "text": "x",
        "char_start": 0,
        "char_end": 1,
        "page": 7,
    }
    assert fusion._text_payload(row)["page"] == 7


def test_visual_payload_is_a_pointer_not_content():
    row = {"chunk_id": "v1", "source_file": "one-line.pdf", "page": 4, "image_path": "/x/4.png"}
    p = fusion._visual_payload(row)
    assert p["kind"] == "visual"
    assert p["text"] is None
    assert p["content_available"] is False
    assert p["locator"] == {"source_file": "one-line.pdf", "page": 4}
    assert "figure transcription" in p["pointer_note"]
    # the old placeholder string must not reappear anywhere in the payload
    assert not any(isinstance(v, str) and v.startswith("[page image") for v in p.values())


def test_extract_snippets_skips_content_unavailable_pointers():
    result = {
        "results": [
            {"text": "Real chunk about CIP-007 R2.", "kind": "text", "content_available": True},
            {
                "text": None,
                "kind": "visual",
                "content_available": False,
                "pointer_note": "page-image match ...",
            },
            # a legacy-shaped placeholder row (no content_available flag) still
            # gets through on its text — but our own visual rows never emit text
            {"text": "another real one", "kind": "text"},
        ]
    }
    snippets = context_inject._extract_snippets(result)
    assert snippets == ["Real chunk about CIP-007 R2.", "another real one"]
    assert not any("page-image" in s for s in snippets)


def test_extract_snippets_still_raises_on_a_truly_unknown_shape():
    import pytest

    with pytest.raises(ValueError, match="unrecognised tool result shape"):
        context_inject._extract_snippets({"weird": 1, "shape": 2})
