"""Content-addressed identity and extraction provenance (P2).

Stable LOGICAL ids group lineage (a document, a requirement, a mapping);
immutable REVISION ids are keyed by full content hash. Filenames/paths are
ALIASES, not identity — re-ingesting identical bytes at any path is
idempotent (same revision id), and replacement bytes at the same path
produce a NEW revision. A caller that wants "the document at this path"
resolves the alias to whichever revision is current; a caller citing an
exact revision id always gets the exact bytes it originally saw, even after
the alias moves on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def content_hash(data: bytes) -> str:
    """Full SHA-256 hex digest — the immutable revision key. Never truncated:
    a truncated hash is an anchor that can silently collide across a large
    corpus, and this task's anchors must resolve exactly (P4.7)."""
    return hashlib.sha256(data).hexdigest()


def text_hash(text: str) -> str:
    return content_hash(text.encode("utf-8"))


@dataclass(frozen=True)
class ExtractionProvenance:
    """How a section/span's text was derived from the source revision bytes —
    kept so a normalization/OCR fix can be distinguished from a genuine
    content change, and so a claim can be traced back to the exact extractor
    version that produced it."""

    extractor: str
    extractor_version: str
    extracted_at: str  # ISO-8601 timestamp
    normalization_map: dict[str, str] = field(default_factory=dict)
