"""Research module hooks for retrieval and wiki claim probes."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from portal.platform.plugins import module_code_present


def document_reader() -> Any | None:
    if not module_code_present("portal.modules.research.tools.rag_mcp"):
        return None
    from portal.modules.research.tools import rag_mcp

    return rag_mcp


def wiki_probes() -> dict[str, Callable[[Path], Any]]:
    return {
        "rag.retrieval.routes": _probe_rag_retrieval_routes,
        "retrieval.stage_set": _probe_retrieval_stage_set,
        "vl.embedding.dim": _probe_vl_embedding_dim,
    }


def _probe_rag_retrieval_routes(root: Path) -> list[str]:
    """The retrieval tool routes registered by rag_multimodal (C4). If ownership
    of kb_search/kb_ingest/kb_search_all moves back to the text-only rag_mcp
    handler this list changes."""
    src = (root / "portal" / "modules" / "research" / "tools" / "rag_multimodal.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"def register_retrieval_routes\(.*?\n(?:(?:    .*)?\n)+", src)
    body = m.group(0) if m else ""
    return sorted(set(re.findall(r'/tools/(kb_\w+)"', body)))


def _probe_retrieval_stage_set(root: Path) -> list[str]:
    """The keys of ``rag_multimodal._stage_set()`` — the knobs stamped into every
    KB at ingest (SEAM V1 P6, SUBSTRATE_MIGRATION_V1 P3). O9: a nominal
    ``modules.enabled contains: research`` probe passed while the subsystem
    carried a wrong diagnosis for five months; this binds the wiki claim to the
    actual stamped stage set, so adding or dropping a stage knob without
    updating the doc fails the census."""
    p = root / "portal" / "modules" / "research" / "tools" / "rag_multimodal.py"
    if not p.is_file():
        return []
    try:
        t = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    m = re.search(r"def _stage_set\(\)[^{]*?return \{(.*?)\n    \}", t, re.S)
    if not m:
        return []
    return sorted(re.findall(r'"([a-z_]+)":', m.group(1)))


def _probe_vl_embedding_dim(root: Path) -> int:
    """The VL retrieval server's declared embedding dim (VL_EMBEDDING_DIM default)."""
    src = (root / "scripts" / "vl-retrieval-server.py").read_text(encoding="utf-8")
    m = re.search(r'VL_EMBEDDING_DIM["\']?,\s*["\'](\d+)["\']', src)
    return int(m.group(1)) if m else -1
