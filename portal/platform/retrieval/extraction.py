"""Document text extraction — moved verbatim from ``rag_multimodal`` (SEAM V1 P2).

Delegates to ``rag_mcp``'s docling extraction with the same fallback chain; the
``rag_mcp`` dependency is unchanged.

SUBSTRATE_MIGRATION_V1 P3.2 adds ``read_document`` — the ``DoclingDocument``
itself, for the ``docling`` chunker — while ``read_text`` keeps returning the
markdown string the ``fixed`` / ``structured`` chunkers consume.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any


async def read_text(path: Path) -> str:
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


async def read_document(path: Path) -> tuple[str, Any | None]:
    """``(markdown_text, DoclingDocument | None)``. The document is present only
    when docling converted a supported format; the text is always populated
    (from the document's markdown export, or the ``read_text`` fallback chain).
    A ``.txt`` / ``.md`` file has text and no document."""
    import asyncio

    from portal.modules.research.tools import rag_mcp

    getdoc = getattr(rag_mcp, "_docling_document", None)
    if getdoc is not None and path.suffix.lower() not in (".txt", ".md"):
        try:
            doc = await asyncio.to_thread(getdoc, path)
            md = doc.export_to_markdown()
            if md and len(md.strip()) > 20:
                return md, doc
        except Exception:  # noqa: BLE001 — fall back to the string path
            pass
    return await read_text(path), None
