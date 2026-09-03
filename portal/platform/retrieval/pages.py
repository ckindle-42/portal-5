"""PDF-page rendering + figure-page selection — moved verbatim from
``rag_multimodal`` (SEAM V1 P2).

``render_pages`` is the only impure part (it shells to pymupdf and writes PNGs);
``figure_pages`` is pure over the ``_PAGE_TEXT_LEN`` map ``render_pages``
populates. Byte-identical to the pre-move bodies (SEAM V1 P4 live-KB parity,
`reports/retrieval/composition_parity.md`).
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_PAGES = int(os.environ.get("RAG_MAX_PAGES", "500"))

# S0: how much extractable text a rendered page had. A page whose text layer is
# already rich is, by definition, covered by the prose chunks — transcribing it
# would duplicate the text arm. Populated by `render_pages`, consumed by
# `figure_pages`.
_PAGE_TEXT_LEN: dict[str, int] = {}
# Below this many characters of extractable text, a page is treated as a figure.
FIGURE_PAGE_MAX_TEXT = int(os.environ.get("RAG_FIGURE_PAGE_MAX_TEXT", "200"))

# SUBSTRATE_MIGRATION_V1 P3.1 (O7). "all" — index every rendered page in the
# visual arm (the pre-P3.1 behaviour: a prose page is then indexed twice, once
# as text chunks and once as a page image, and searched with the same qvec —
# the collision VL_TEXT_GATE exists to referee). "figures" — index only the
# pages `figure_pages` keeps, so a prose page lives in the text arm only.
VISUAL_SCOPE = os.environ.get("RAG_VISUAL_SCOPE", "all")


def render_pages(pdf_path: str, out_dir: Path, dpi: int = 150) -> list:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    doc = pymupdf.open(pdf_path)
    for i, page in enumerate(doc):
        if i >= MAX_PAGES:
            break
        p = out_dir / f"{Path(pdf_path).stem}_p{i:04d}.png"
        page.get_pixmap(dpi=dpi).save(str(p))
        pages.append((i, str(p)))
        _PAGE_TEXT_LEN[str(p)] = len(page.get_text().strip())
    doc.close()
    return pages


def figure_pages(pages: list) -> list:
    """S0: the subset of pages worth transcribing.

    Deterministic, not model-judgement. The obvious design — prompt the vision
    model to answer NONE on a body-text page — was measured and does not hold:
    the strongest transcribers are OCR models that transcribe *everything*
    (glm-ocr, Nanonets-OCR2, minicpm-v4.5 all scored 0/4 on NONE discipline).
    Trusting self-abstention would duplicate every prose page into the text arm.
    PyMuPDF already tells us the text-layer length for free during render, so
    the filter is exact and costs nothing — and it makes NONE discipline
    irrelevant to model selection."""
    return [(pn, img) for pn, img in pages if _PAGE_TEXT_LEN.get(img, 0) < FIGURE_PAGE_MAX_TEXT]
