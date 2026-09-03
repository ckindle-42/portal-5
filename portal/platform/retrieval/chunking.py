"""Text chunking stage — moved verbatim from ``rag_multimodal`` (SEAM V1 P2).

Pure functions: no services, no models. Byte-identical to the pre-move bodies —
see `reports/retrieval/composition_parity.md` (P4). The leading underscore is
dropped where a function becomes library API; ``rag_multimodal`` keeps thin
aliases for the transition.
"""

from __future__ import annotations

import os
import re

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))

# Boundaries that mean something in a standards/procedure corpus. Ordered
# strongest-first; all are matched at line start on the PyMuPDF text layer (the
# host venv has no docling, so there are no markdown headings to lean on).
SECTION_BOUNDARY = re.compile(
    r"(?m)^[ \t]*(?:"
    r"#{1,6}[ \t]+"  # markdown heading, when docling IS available
    r"|R\d+(?:\.\d+)*\.?[ \t]"  # NERC requirement: R1. / R1.2.
    r"|[A-Z]\.[ \t]+(?=[A-Z])"  # lettered section: "A. Introduction"
    r"|\d+\.\d+(?:\.\d+)*\.?[ \t]"  # numbered part: 4.1 / 4.1.1
    r"|(?:Attachment|Appendix|Table|Requirement)[ \t]+\w"
    r")"
)


def chunk_fixed(text: str, size: int, overlap: int) -> list:
    out, i = [], 0
    while i < len(text):
        seg = text[i : i + size]
        if seg.strip():
            out.append((i, i + len(seg), seg))
        i += max(1, size - overlap)
    return out


def chunk_structured(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Split on document structure, then pack — instead of slicing blind.

    Fixed-width slicing cuts mid-requirement and needs an overlap purely to heal
    the cuts it made. Splitting on real boundaries (requirement / section /
    numbered part) means a chunk is a whole unit, so the overlap is only needed
    for the rare unit that is itself larger than `size`."""
    marks = [m.start() for m in SECTION_BOUNDARY.finditer(text)]
    if len(marks) < 2:  # nothing to go on — fixed slicing is the honest fallback
        return chunk_fixed(text, size, overlap)
    bounds = sorted({0, *marks, len(text)})
    units = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    out: list = []
    cs = ce = None
    for s, e in units:
        if e - s > size:  # an oversized unit still has to be sliced
            if cs is not None:
                out.append((cs, ce, text[cs:ce]))
                cs = ce = None
            for a, b, seg in chunk_fixed(text[s:e], size, overlap):
                out.append((s + a, s + b, seg))
            continue
        if cs is None:
            cs, ce = s, e
        elif e - cs <= size:
            ce = e  # pack adjacent units up to the budget
        else:
            out.append((cs, ce, text[cs:ce]))
            cs, ce = s, e
    if cs is not None:
        out.append((cs, ce, text[cs:ce]))
    return [(a, b, t) for a, b, t in out if t.strip()]


# `fixed` is blind character slicing; `structure` splits on requirement/section
# boundaries. Default is `fixed` because structure LOST when measured against a
# docling-extracted corpus: prose recall@1 0.875 -> 0.750 (2356 chunks vs 2138).
# Splitting on my own regex boundaries fragments groupings docling's layout model
# already got right — the structure chunker was solving a problem that only
# existed while extraction was falling back to raw PyMuPDF text. Kept available
# for a corpus with no usable extractor.
CHUNK_STRATEGY = os.environ.get("RAG_CHUNK_STRATEGY", "fixed")


def chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    if CHUNK_STRATEGY == "fixed":
        return chunk_fixed(text, size, overlap)
    return chunk_structured(text, size, overlap)
