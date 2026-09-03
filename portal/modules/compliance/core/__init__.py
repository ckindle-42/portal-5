"""Compliance reasoning engine (TASK_COMPLIANCE_ENGINE_V1, program track T3).

A *second composition* of the retrieval stage library — its own routes, its own
tables, its own pipeline stages. It changes no shared retrieval behaviour and
invalidates no other consumer's index (`compliance_*` tables only).

Not a RAG chatbot. Four properties, none a retrieval parameter:

1. temporal validity filters *before* ranking (a `.where()` predicate);
2. authority tiers have precedence — a cross-tier contradiction is emitted,
   never reconciled;
3. gaps come from enumeration over the requirement register, not from asking;
4. settled `requirement -> document` mappings are human-owned and double as the
   evaluation set.
"""

from __future__ import annotations
