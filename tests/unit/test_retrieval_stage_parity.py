"""Byte-identical parity between the extracted stages and their pre-refactor bodies.

TASK_RAG_COMPOSITION_SEAM_V1 P2.2. The composition seam is a pure refactor: every
stage must return exactly what it returned before it moved. These are pure
functions, so parity is checkable with no services and no models — which makes this
the cheapest possible guard on the most dangerous kind of change.

`tests/fixtures/retrieval_legacy.py` holds the pre-move bodies verbatim. Delete both
that fixture and this module in P5, once end-to-end parity (P4) has also passed.
"""

from __future__ import annotations

import pytest

from portal.platform.retrieval import chunking, pages
from tests.fixtures import retrieval_legacy as legacy

# Inputs chosen to exercise the branches that actually differ: boundary-dense
# regulatory text, a unit larger than `size` (forces the slice path), text with
# fewer than two boundary marks (forces the fixed fallback), and empty input.
_CASES = [
    "",
    "short",
    "R1. Alpha\nR1.1 Beta\nR2. Gamma\n" * 40,
    "# Heading\n\n" + ("body sentence. " * 500),
    "Attachment 1\n" + ("x" * 3000) + "\nRequirement R3.\n",
    "\n".join(f"4.{i}.1 Part text {i}" for i in range(200)),
]


@pytest.mark.parametrize("text", _CASES)
@pytest.mark.parametrize("size,overlap", [(1000, 150), (250, 0), (5000, 400)])
def test_chunk_fixed_is_byte_identical(text, size, overlap):
    assert chunking.chunk_fixed(text, size, overlap) == legacy._chunk_fixed(text, size, overlap)


@pytest.mark.parametrize("text", _CASES)
@pytest.mark.parametrize("size,overlap", [(1000, 150), (250, 0), (5000, 400)])
def test_chunk_structured_is_byte_identical(text, size, overlap):
    assert chunking.chunk_structured(text, size, overlap) == legacy._chunk_structured(
        text, size, overlap
    )


@pytest.mark.parametrize("text", _CASES)
def test_section_boundary_matches_identically(text):
    assert [m.span() for m in chunking.SECTION_BOUNDARY.finditer(text)] == [
        m.span() for m in legacy._SECTION_BOUNDARY.finditer(text)
    ]


def test_figure_pages_selection_is_byte_identical():
    fixture = [(i, f"/tmp/p{i}.png") for i in range(12)]
    lengths = {f"/tmp/p{i}.png": (0 if i % 3 else 900) for i in range(12)}
    pages._PAGE_TEXT_LEN.update(lengths)
    legacy._PAGE_TEXT_LEN.update(lengths)
    assert pages.figure_pages(fixture) == legacy._figure_pages(fixture)


def test_chunk_dispatch_honours_strategy_identically(monkeypatch):
    text = _CASES[2]
    for strategy in ("fixed", "structured"):
        monkeypatch.setattr(chunking, "CHUNK_STRATEGY", strategy)
        monkeypatch.setattr(legacy, "CHUNK_STRATEGY", strategy)
        assert chunking.chunk(text) == legacy._chunk(text)
