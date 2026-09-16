"""Compliance reasoning engine (TASK_COMPLIANCE_ENGINE_V1, program track T3).

A *second composition* of the retrieval stage library — its own routes, its own
tables, its own pipeline stages. It changes no shared retrieval behaviour and
invalidates no other consumer's index (`compliance_*` tables only).

Not a RAG chatbot. Four properties, none a retrieval parameter — and since
SUBSTRATE_PROPERTIES_V1, four properties that EXIST, each with the module and
function that delivers it:

1. temporal validity filters *before* ranking — the projection carries the
   predicate columns (`section_index.PREDICATE_COLUMNS`,
   `section_index.build_plan`), the shared seam applies them under ranking
   (`portal/platform/retrieval/pipeline.search(where=…)` →
   `fusion.fuse` → both arms), and `compliance_mcp._search_predicate` builds
   the clock clauses against their `""` open-bound convention;
2. authority tiers have precedence — a cross-tier contradiction is emitted,
   never reconciled: every section resolves with its recorded tier
   (`tiers.recorded_tier`, projected as `authority_tier`), and contradiction is
   a retrievable fact on the reading path
   (`reading_assembly.conflicts_for_requirement`, the `compliance_conflicts`
   tool and the assembly's `conflicts` component), not a verdict-engine
   byproduct;
3. gaps come from enumeration over the requirement register, not from asking —
   `enumeration.declared_population` reads a whole declared population with its
   boundary receipt, and `assessment_source.acquire_exhaustively` is one caller
   of it;
4. settled `requirement -> document` mappings are human-owned and double as the
   evaluation set — `evaluation.labelled_examples` exports them,
   `evaluation.as_eval_set` is the shape a WFE suite binds, and
   `evaluation.score_reading` measures citation behaviour offline. Nothing in
   the product path imports the scorer.
"""

from __future__ import annotations
