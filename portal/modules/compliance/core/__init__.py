"""Compliance reasoning engine (TASK_COMPLIANCE_ENGINE_V1, program track T3).

A *second composition* of the retrieval stage library — its own routes, its own
tables, its own pipeline stages. It changes no shared retrieval behaviour and
invalidates no other consumer's index (`compliance_*` tables only).

Not a RAG chatbot. Four properties, none a retrieval parameter — and since
SUBSTRATE_PROPERTIES_V1, four properties that EXIST, each with the module and
function that delivers it:

1. filters run *before* ranking, and **the predicate that matters is
   requirement identity** — not only the document-derived clocks. A question
   about CIP-007-6 R2 Part 2.2 is a question about *that requirement's
   sections*, and until ONE_REGULATORY_EXTRACTION_V1 the store could not
   express it: `RegisterNode` carried no `section_id`, `source_sections`
   carried no requirement reference, and the only overlap was page
   granularity. `requirement_sections` is that key
   (`requirement_anchor` anchors it by exact match,
   `Repository.sections_for_requirement` / `requirements_for_section` read it
   both ways), and `compliance_mcp._requirement_predicate` resolves a
   requirement to exact ids pushed as `chunk_id IN (…)`. The clocks compose
   with it by `AND`: the projection carries the predicate columns
   (`section_index.PREDICATE_COLUMNS`, `section_index.build_plan`), the shared
   seam applies them under ranking
   (`portal/platform/retrieval/pipeline.search(where=…)` → `fusion.fuse` →
   both arms), and `compliance_mcp._search_predicate` builds the clock clauses
   against their `""` open-bound convention;
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
