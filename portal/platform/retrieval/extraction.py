"""Document text extraction — moved verbatim from ``rag_multimodal`` (SEAM V1 P2).

Delegates to ``rag_mcp``'s docling extraction with the same fallback chain; the
``rag_mcp`` dependency is unchanged.
"""

from __future__ import annotations

import contextlib
from pathlib import Path


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
