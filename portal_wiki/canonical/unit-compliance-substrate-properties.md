---
id: unit-compliance-substrate-properties
kind: mixed
title: "Compliance substrate — enumeration and the mapping evaluation set"
sources:
- type: code
  path: portal/modules/compliance/core/enumeration.py
- type: code
  path: portal/modules/compliance/core/search_service.py
- type: code
  path: tests/unit/test_compliance_reading_boundaries.py
- type: code
  path: portal/modules/compliance/core/evaluation.py
claims:
- probe: modules.enabled
  contains: compliance
confidence: high
tags:
- authored-v1
- compliance
- substrate-properties
---

SUBSTRATE_PROPERTIES_V1 gave the compliance module's four founding properties
implementations; the two files documented here are property 3 and property 4.

## Why

For a year the module's founding docstring described four properties that did
not exist — the only `.where(` in the module was the docstring's own claim, and
the declared evaluation set had never been wired. Four generations of reasoning
layer were built on that docstring. These two files are the parts of the fix
that outlive any one retrieval call: a population you can name (so an absence
claim is checkable) and a ground truth that grows every time an SME approves a
mapping (so a seat can be scored instead of argued).

## Enumeration — property 3's population primitive

`declared_population(repo, *, jurisdiction, scope_sections=None)` reads a whole
declared population straight from the canonical store
(`section_index.build_plan`), resolves every section verbatim, and emits the
boundary receipt that says what was eligible, what was examined, and what is
missing. Gaps come from enumeration over a named population, not from asking a
retriever. One implementation, three consumers: `assessment_source.
acquire_exhaustively` (reduced to a caller), file B's closure, file D's
`compliance_orphans`.

## Evaluation — property 4's instrument

`mapping_store` has always said every approved mapping is a labelled example;
`labelled_examples(repo)` is the first thing to use them that way — settled
`requirement → section` pairs with who approved, when, whether it was a
correction, plus explicitly rejected mappings as labelled negatives.
`as_eval_set` is the shape a WFE suite binds. `score_reading` measures citation
behaviour only — recall, precision over labelled citations (unmapped citations
are `unlabelled`, never wrong), rejected-mapping avoidance, closure honesty.
An empty labelled set is `honest-BLOCKED` naming the shortfall, never a zero.

Two disciplines are load-bearing: the scorer is an OFFLINE instrument — a test
walks `portal/` and fails if anything outside `evaluation.py` imports it — and
it is validated against the hand-judged seat-probe transcripts before it is
trusted (with zero approved mappings it blocks on all of them, by name).

## The search composition — property 1, in one place

`core/search_service.search` is the whole compliance search: addressed hits
resolved directly, then the arms scored over a pushed-down `.where()`
predicate. Every filter — the clocks, the standard, the layer, the requirement
identity — is composed BEFORE ranking, so a filter targets the search rather
than shrinking its aftermath. A filter that runs after ranking and one that runs
before it produce the same count and completely different evidence.

It lives in `core/` rather than in the MCP tool because it has two callers.
`tools/compliance_mcp.compliance_search` and the reader's own
`core/reading_tools.compliance_search` are both thin delegations. The reader's
tool had grown a second implementation — retrieve an unscoped top-k, then drop
the results not joined to `requirement` — which is the keyhole this predicate
exists to remove, rebuilt beside it. Because that copy filtered against
`sections_for_requirement`, which holds the REGULATORY anchors, passing
`requirement=` also discarded every operator hit: a bilateral search that could
not return the operator's side, in the one tool a bilateral reading uses to find
it.

`requirement` narrows by identity through `core/requirement_scope`, so the pool
is bilateral (the requirement's anchors AND the operator sections recorded as
related to it) and a parent requirement reaches its Parts through the register
rather than by string prefix.
