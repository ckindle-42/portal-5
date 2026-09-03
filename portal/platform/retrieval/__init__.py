"""Portal 5 retrieval substrate — the shared stage library.

TASK_RAG_COMPOSITION_SEAM_V1. The seam between the general RAG and the compliance
engine is *composition, not configuration*: one implementation of each retrieval
primitive, composed two ways. ``portal.modules.research.tools.rag_multimodal`` is
the first composition (the ``kb_*`` tools, byte-identical to its pre-seam
behaviour); ``portal.modules.compliance.tools.compliance_retrieval`` is the
second, with its own routes and its own tables.

Stages:

* ``chunking`` — pure text → chunk spans (fixed / structured / dispatch).
* ``pages``    — pure PDF-page rendering + figure-page selection.
* ``extraction`` — document text extraction (delegates to ``rag_mcp``).

Service-touching stages (embedding, store, fusion, pipeline) are extracted in
Phase 3.
"""

from __future__ import annotations
