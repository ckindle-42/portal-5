"""Pre-move bodies of the retrieval stages, VERBATIM.

Taken from ``portal/modules/research/tools/rag_multimodal.py`` at commit
``3de59b6c`` (TASK_RAG_COMPOSITION_SEAM_V1 P1), immediately before P2 extracted
these functions into ``portal.platform.retrieval``.

This file exists ONLY to be diffed against the extracted stages by
``tests/unit/test_retrieval_stage_parity.py``. It is deleted in P5 once
end-to-end composition parity (P4) has also passed. Do not import it from
anything but that parity test, and do not "fix" anything here — a divergence
from this file is the signal the refactor changed behaviour.
"""

from __future__ import annotations

import contextlib
import os
import re
from pathlib import Path

CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "150"))
_MAX_PAGES = int(os.environ.get("RAG_MAX_PAGES", "500"))

_SECTION_BOUNDARY = re.compile(
    r"(?m)^[ \t]*(?:"
    r"#{1,6}[ \t]+"  # markdown heading, when docling IS available
    r"|R\d+(?:\.\d+)*\.?[ \t]"  # NERC requirement: R1. / R1.2.
    r"|[A-Z]\.[ \t]+(?=[A-Z])"  # lettered section: "A. Introduction"
    r"|\d+\.\d+(?:\.\d+)*\.?[ \t]"  # numbered part: 4.1 / 4.1.1
    r"|(?:Attachment|Appendix|Table|Requirement)[ \t]+\w"
    r")"
)


def _chunk_fixed(text: str, size: int, overlap: int) -> list:
    out, i = [], 0
    while i < len(text):
        seg = text[i : i + size]
        if seg.strip():
            out.append((i, i + len(seg), seg))
        i += max(1, size - overlap)
    return out


def _chunk_structured(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    marks = [m.start() for m in _SECTION_BOUNDARY.finditer(text)]
    if len(marks) < 2:  # nothing to go on — fixed slicing is the honest fallback
        return _chunk_fixed(text, size, overlap)
    bounds = sorted({0, *marks, len(text)})
    units = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    out: list = []
    cs = ce = None
    for s, e in units:
        if e - s > size:  # an oversized unit still has to be sliced
            if cs is not None:
                out.append((cs, ce, text[cs:ce]))
                cs = ce = None
            for a, b, seg in _chunk_fixed(text[s:e], size, overlap):
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


CHUNK_STRATEGY = os.environ.get("RAG_CHUNK_STRATEGY", "fixed")


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    if CHUNK_STRATEGY == "fixed":
        return _chunk_fixed(text, size, overlap)
    return _chunk_structured(text, size, overlap)


def _render_pages(pdf_path: str, out_dir: Path, dpi: int = 150) -> list:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    doc = pymupdf.open(pdf_path)
    for i, page in enumerate(doc):
        if i >= _MAX_PAGES:
            break
        p = out_dir / f"{Path(pdf_path).stem}_p{i:04d}.png"
        page.get_pixmap(dpi=dpi).save(str(p))
        pages.append((i, str(p)))
        _PAGE_TEXT_LEN[str(p)] = len(page.get_text().strip())
    doc.close()
    return pages


_PAGE_TEXT_LEN: dict[str, int] = {}
FIGURE_PAGE_MAX_TEXT = int(os.environ.get("RAG_FIGURE_PAGE_MAX_TEXT", "200"))


def _figure_pages(pages: list) -> list:
    return [(pn, img) for pn, img in pages if _PAGE_TEXT_LEN.get(img, 0) < FIGURE_PAGE_MAX_TEXT]


async def _read_text(path: Path) -> str:
    """Reuse rag_mcp's docling extraction; fall back to plain read for text."""
    from portal.modules.research.tools import rag_mcp

    reader = getattr(rag_mcp, "_read_file", None)
    if reader is not None:
        with contextlib.suppress(Exception):
            return await reader(path)
    conv = getattr(rag_mcp, "_docling_convert", None)
    if conv is not None:
        with contextlib.suppress(Exception):
            return conv(path)
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(errors="ignore")
    return ""
