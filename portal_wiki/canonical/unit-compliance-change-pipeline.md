---
id: unit-compliance-change-pipeline
kind: mixed
title: "Compliance change pipeline — register diff and impact traversal"
sources:
- type: code
  path: portal/modules/compliance/core/register_diff.py
- type: code
  path: portal/modules/compliance/core/change_pipeline.py
- type: code
  path: tests/unit/test_compliance_change_pipeline.py
claims:
- probe: compliance.change_types
  contains: LANGUAGE_CHANGED
- probe: compliance.change_types
  contains: RENUMBERED
- probe: compliance.change_types
  contains: TIMELINE_CHANGED
- probe: compliance.register
  contains: CIP-003-8
- probe: compliance.register
  contains: CIP-003-9
confidence: high
tags:
- compliance
- authored-v1
---

`portal.modules.compliance.core.register_diff` + `change_pipeline`
(TASK_COMPLIANCE_CHANGE_PIPELINE_V1) answer the half of the use case T3 does
not: *"what just changed between two versions of a standard, and what do we now
have to do about it."* A gap is a static property of today's register against
today's policy; a **change** is a delta between two register states, propagated
through the mapping edges to the policy sections that have to move.

## Register diff (Phase 1)

`diff_standard(old, new, "CIP-003")` emits a **typed** Part-level diff over the
eight change types (`PART_ADDED`, `PART_REMOVED`, `LANGUAGE_CHANGED`,
`APPLICABILITY_CHANGED`, `TIMELINE_CHANGED`, `EVIDENCE_CHANGED`,
`SEVERITY_CHANGED`, `RENUMBERED`). Structural change is a set difference; the
case that matters is a Part that survives with **modified language**, so
`LANGUAGE_CHANGED` is sub-classified:

- `modality` — a deontic modal changed (`shall` ⇄ `should`/`may`)
- `timeline` — a numeric duration/deadline changed (raised as `TIMELINE_CHANGED`)
- `evidence` — the measure text changed
- `substantive` — other wording that alters the obligation
- `cosmetic` — punctuation / whitespace / a moved list conjunction only —
  **never raised as an obligation change**

`RENUMBERED` needs a high similarity threshold (`_RENUMBER_HI = 0.90`); below
`_RENUMBER_LO = 0.60` it is a genuine add/remove, and between the two it is
`needs_review` — a Part is never paired silently. A **shift-insert** (an item
inserted into a nested list pushes every id below it down one) is detected by
matching casefolded verbatim text across ids, so `CIP-003-8 1.2.6 → CIP-003-9
1.2.7` is one `RENUMBERED` row, not an add + a remove.

**Every diff row carries both verbatim spans**, old and new. `to_dict()["substantive"]`
is the single predicate the rest of the pipeline gates on (`False` only for a
cosmetic `LANGUAGE_CHANGED`).

## Impact traversal, mapping expiry, prospective (Phases 2, 4, 5)

- `impact_report(old, new, base, scope, store)` — for each **substantive** diff
  row, traverse `store.all_for()` to the policy/procedure sections that
  implemented the affected Part, mark their prior verdict *unverified*, and gate
  on `applicable()`: a change to a Part outside the declared `AssetScope` is
  **informational**, not work. Requires a declared scope (the T3 `[GATE]`).
  `examined` is reported apart from `substantively_resolved` (Bully GP).
- `expire_mappings(store, rows, date)` — every mapping whose target Part is
  `RENUMBERED` / `LANGUAGE_CHANGED` / `TIMELINE_CHANGED` / `PART_REMOVED` has its
  `valid_to` closed and a successor created as `NEEDS_REVIEW` with
  `source="successor_of_expired"` and `confidence=0.0` — **the prior verdict is
  never inherited across a language change.**
- `prospective_report(reg, scope, as_of)` — the same traversal against
  `future_effective_parts`; every row is `prospective: True` and the enforcement
  date is *"SEE Implementation Plan — verify, do not infer"* when the register
  has no `valid_from`. It MUST NOT reach a "what must we do today" answer.

## Drafted revisions — [GATE] (Phase 6)

`draft_revisions(impact)` is **specification-only**: it outputs *what* section
must change, *why*, and both verbatim spans, and leaves the language to an SME.
Modes (b) draft-as-proposal and (c) draft-into-revision raise `NotImplementedError`
— they are the operator's decision (report, do not choose). Recommendation on
the operator's desk: (a) is the capability with no new risk surface; a draft
reads as finished work and is accepted more uncritically than a gap statement
(`granite-4.1-8b` was demoted from this persona for fabricating regulatory
requirements).

## Verified transition

`CIP-003-8 → CIP-003-9`: 13 diff rows — **1 `RENUMBERED`** (1.2.6→1.2.7,
shift-insert), **2 substantive `LANGUAGE_CHANGED`** (new 1.2.6 "Vendor
electronic remote access security controls"; R2 lead-in), **10 cosmetic**
(U+2010 hyphen re-encoding on the 1.1.x topic list + a moved `; and`
conjunction). The new vendor-remote-access **Attachment 1 Section 6** is a known
false negative — Attachment content is the documented T3 Phase 1 extraction
shortfall, not a diff-engine defect. See
[[unit-known-limitations-compliance-implicit-change-recall]] and
[[unit-compliance-engine]].

## Why

NERC publishes a new CIP version and the one-time gap report from T3 goes stale.
Without a diff that is *typed* and *sub-classified*, every version bump produces
an alert stream where a moved comma and a changed deadline look the same — and an
alert stream full of typo notifications gets muted, taking the real alerts with
it. So cosmetic change is suppressed by construction and its false-positive rate
is measured separately from change-detection recall, never averaged: a missed
change is a silently stale policy, the same institutional-risk asymmetry that
makes Full-Gap recall the headline in T3. The mapping-expiry rule is the other
load-bearing invariant — an SME approved "this policy section fully implements
Part 1.2.6"; when 1.2.6 changes meaning, carrying that FULL verdict forward is
how a compliance tool silently starts lying.
