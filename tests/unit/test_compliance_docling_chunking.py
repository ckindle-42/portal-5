"""Y25 — the compliance composition must actually get docling chunking.

`chunking.chunk(strategy="docling")` uses the layout-aware HybridChunker only
when it is handed a DoclingDocument. Given `doc=None` it falls back to
`chunk_fixed` — blind character slicing, `page=-1`, `headings=""` — and it does
so SILENTLY, via both a `doc is None` branch and a bare `except Exception`.

The compliance composition declared `chunk_strategy: "docling"` in its stage-set
and `contextualize=True` ("embed heading path + text"), but never supplied
`read_document`. Result, measured on the 14-PDF CIP corpus: 1508 of 1508 chunks
at page=-1 with an empty heading path, and a contextualize stage with nothing to
contextualize. These tests pin the wiring, not the model output.
"""

from __future__ import annotations

import importlib

cr = importlib.import_module("portal.modules.compliance.tools.compliance_retrieval")
chunking = importlib.import_module("portal.platform.retrieval.chunking")
extraction = importlib.import_module("portal.platform.retrieval.extraction")


def test_composition_requests_docling_chunking():
    assert cr._COMPLIANCE_CHUNK_STRATEGY == "docling"
    assert cr._composition().stage_set["chunk_strategy"] == "docling"


def test_composition_supplies_the_document_docling_needs():
    """The bug: strategy said docling, nothing ever produced a DoclingDocument.
    A composition that asks for docling chunking MUST set read_document, or it
    silently gets fixed slicing with the docling label stamped on the KB."""
    comp = cr._composition()
    assert comp.read_document is not None, (
        "chunk_strategy is 'docling' but read_document is None — every chunk "
        "will silently fall back to chunk_fixed with page=-1 and headings=''"
    )
    assert comp.read_document is extraction.read_document


def test_contextualize_is_only_meaningful_with_a_heading_source():
    """contextualize embeds the heading path with the text. Only the docling
    chunker produces one, so contextualize without it is a declared no-op."""
    comp = cr._composition()
    if comp.contextualize:
        assert comp.read_document is not None, (
            "contextualize=True embeds a heading path that only the docling "
            "chunker produces; without read_document there is never one"
        )


def test_fixed_fallback_is_what_empty_headings_look_like():
    """Pins the signature of the failure, so the assertions above have teeth:
    the fallback really does yield page=-1 and headings='' for every chunk."""
    rows = chunking.chunk("a" * 3000, None, strategy="docling")
    assert rows, "fallback produced no chunks"
    assert all(page == -1 for *_, page, _ in rows)
    assert all(headings == "" for *_, headings in rows)


def test_docling_strategy_without_doc_does_not_raise():
    """The fallback must stay graceful — this test exists so nobody 'fixes' the
    silent fallback by making it throw at ingest time. The fix is to supply the
    document (test above), not to crash the pipeline for .txt inputs, which
    legitimately have no DoclingDocument."""
    assert chunking.chunk("short text", None, strategy="docling") is not None
