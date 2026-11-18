"""T2 P3.2 — the chunk contract is a 5-tuple (char_start, char_end, text, page,
headings) for every strategy, so `fixed` / `structured` rows shape like the
`docling` rows that carry real page + heading provenance.
"""

from __future__ import annotations

import importlib

ck = importlib.import_module("portal.platform.retrieval.chunking")

_TEXT = (
    "R1. The Responsible Entity shall implement a documented process.\n"
    "1.1 The process shall address identification.\n" + ("padding sentence. " * 120) + "\n"
    "1.2 The process shall address classification.\n" + ("more padding. " * 120)
)


def test_char_offsets_index_the_source():
    rows = ck.chunk(_TEXT)
    for cs, ce, text, _p, _h in rows:
        assert _TEXT[cs:ce] == text
