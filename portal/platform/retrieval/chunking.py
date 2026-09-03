"""Text chunking stage — moved verbatim from ``rag_multimodal`` (SEAM V1 P2).

Pure functions: no services, no models. Byte-identical to the pre-move bodies —
see `reports/retrieval/composition_parity.md` (P4). The leading underscore is
dropped where a function becomes library API; ``rag_multimodal`` keeps thin
aliases for the transition.
"""

from __future__ import annotations

import os
import re
from typing import Any

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))
# SUBSTRATE_MIGRATION_V1 P3.2: token budget for the docling HybridChunker. The
# VL embedding model's context is large; 480 tokens keeps a chunk focused and
# roughly matches the ~1000-char fixed window so the arms stay comparable.
DOCLING_MAX_TOKENS = int(os.environ.get("RAG_DOCLING_MAX_TOKENS", "480"))
# Tokenizer the HybridChunker counts with — a small HF tokenizer, NOT the VL
# model (which has no HF tokenizer id). Only used for length control.
DOCLING_TOKENIZER = os.environ.get(
    "RAG_DOCLING_TOKENIZER", "sentence-transformers/all-MiniLM-L6-v2"
)

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


_chunker = None


def _hybrid_chunker():
    global _chunker
    if _chunker is None:
        from docling.chunking import HybridChunker

        _chunker = HybridChunker(
            tokenizer=DOCLING_TOKENIZER, max_tokens=DOCLING_MAX_TOKENS, merge_peers=True
        )
    return _chunker


def chunk_docling(doc: Any, markdown: str = "") -> list:
    """SUBSTRATE_MIGRATION_V1 P3.2 (O5). Chunk the ``DoclingDocument`` with the
    layout-aware ``HybridChunker`` instead of regexing section boundaries over a
    markdown export. Each chunk carries the docling ``prov.page_no`` (1-indexed)
    and its heading path, both discarded by the pre-P3.2 markdown path.

    Returns 5-tuples ``(char_start, char_end, text, page, headings)``. Char
    offsets are located in ``markdown`` best-effort (O2's locator field); a chunk
    whose text is reflowed past a literal match reports ``(0, len(text))``."""
    hc = _hybrid_chunker()
    out: list = []
    for ch in hc.chunk(dl_doc=doc):
        text = ch.text
        if not text or not text.strip():
            continue
        meta = getattr(ch, "meta", None)
        headings = " > ".join(getattr(meta, "headings", None) or [])
        page = -1
        for di in getattr(meta, "doc_items", None) or []:
            prov = getattr(di, "prov", None) or []
            if prov and getattr(prov[0], "page_no", None) is not None:
                page = int(prov[0].page_no)
                break
        pos = markdown.find(text[:200]) if markdown else -1
        cs = pos if pos >= 0 else 0
        ce = pos + len(text) if pos >= 0 else len(text)
        out.append((cs, ce, text, page, headings))
    return out


# `fixed` is blind character slicing; `structure` splits on requirement/section
# boundaries with a hand-rolled regex; `docling` uses docling's layout-aware
# HybridChunker on the DoclingDocument itself. `structure` LOST to `fixed` on a
# docling-extracted corpus (prose r@1 0.875 -> 0.750) — but that compared a regex
# to blind slicing, NOT docling's own chunker, which was never in the running.
# SUBSTRATE_MIGRATION_V1 P3.2 re-runs `docling` vs `fixed` per KB; see
# reports/retrieval/SUBSTRATE_MIGRATION_V1.md for the verdict and its corpus.
CHUNK_STRATEGY = os.environ.get("RAG_CHUNK_STRATEGY", "fixed")


def _to5(rows: list) -> list:
    """Normalise a 3-tuple chunk list to the 5-tuple contract (page -1, no
    headings) so ``fixed`` / ``structured`` rows shape like ``docling`` rows."""
    return [(cs, ce, t, -1, "") for cs, ce, t in rows]


def chunk(
    text: str,
    doc: Any | None = None,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list:
    """5-tuples ``(char_start, char_end, text, page, headings)``. ``doc`` is the
    optional ``DoclingDocument`` — required only for ``CHUNK_STRATEGY=docling``,
    which falls back to ``fixed`` when it is absent."""
    if CHUNK_STRATEGY == "docling":
        if doc is not None:
            try:
                return chunk_docling(doc, text)
            except Exception:  # noqa: BLE001 — a chunker failure degrades, doesn't crash ingest
                pass
        return _to5(chunk_fixed(text, size, overlap))
    if CHUNK_STRATEGY == "fixed":
        return _to5(chunk_fixed(text, size, overlap))
    return _to5(chunk_structured(text, size, overlap))
