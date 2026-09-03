"""T2 P3.2 — the chunk contract is a 5-tuple (char_start, char_end, text, page,
headings) for every strategy, so `fixed` / `structured` rows shape like the
`docling` rows that carry real page + heading provenance.
"""

from __future__ import annotations

import importlib

import pytest

ck = importlib.import_module("portal.platform.retrieval.chunking")

_TEXT = (
    "R1. The Responsible Entity shall implement a documented process.\n"
    "1.1 The process shall address identification.\n" + ("padding sentence. " * 120) + "\n"
    "1.2 The process shall address classification.\n" + ("more padding. " * 120)
)


@pytest.mark.parametrize("strategy", ["fixed", "structured"])
def test_every_row_is_a_5tuple(monkeypatch, strategy):
    monkeypatch.setattr(ck, "CHUNK_STRATEGY", strategy)
    rows = ck.chunk(_TEXT)
    assert rows
    for cs, ce, text, page, headings in rows:  # unpacks == exactly 5
        assert isinstance(cs, int) and isinstance(ce, int) and ce >= cs
        assert isinstance(text, str) and text.strip()
        assert page == -1  # only the docling chunker knows the page
        assert headings == ""


def test_docling_strategy_without_a_document_falls_back_to_fixed(monkeypatch):
    monkeypatch.setattr(ck, "CHUNK_STRATEGY", "docling")
    rows = ck.chunk(_TEXT, doc=None)
    assert rows and all(len(r) == 5 and r[3] == -1 for r in rows)
    # identical to the fixed result — the fallback is fixed, not structured
    monkeypatch.setattr(ck, "CHUNK_STRATEGY", "fixed")
    assert [r[2] for r in rows] == [r[2] for r in ck.chunk(_TEXT)]


def test_char_offsets_index_the_source():
    rows = ck.chunk(_TEXT)
    for cs, ce, text, _p, _h in rows:
        assert _TEXT[cs:ce] == text
