---
id: unit-compliance-substrate-properties
kind: mixed
title: "Compliance substrate — enumeration and the mapping evaluation set"
sources:
- type: code
  path: portal/modules/compliance/core/enumeration.py
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

## enumeration — property 3's population primitive

`declared_population(repo, *, jurisdiction, scope_sections=None)` reads a whole
declared population straight from the canonical store
(`section_index.build_plan`), resolves every section verbatim, and emits the
boundary receipt that says what was eligible, what was examined, and what is
missing. Gaps come from enumeration over a named population, not from asking a
retriever. One implementation, three consumers: `assessment_source.
acquire_exhaustively` (reduced to a caller), file B's closure, file D's
`compliance_orphans`.

## evaluation — property 4's instrument

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
