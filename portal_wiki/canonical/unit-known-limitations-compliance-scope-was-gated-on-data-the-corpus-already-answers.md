---
id: unit-known-limitations-compliance-scope-was-gated-on-data-the-corpus-already-answers
kind: what
title: "KNOWN_LIMITATIONS — do not gate on a question the data answers"
sources:
- type: code
  path: portal/modules/compliance/core/applicability.py
- type: code
  path: portal/modules/compliance/core/scope_derive.py
claims: []
confidence: high
tags:
- docs
- verified-v1
---
### Do not gate on a question the data answers (RESOLVED)

- **ID**: T5-COMPLIANCE-LANDING-002
- **Status**: RESOLVED `TASK_COMPLIANCE_ENGINE_LANDING_V1` Phase 4.
  `applicability.py`'s own docstring asserted: *"Asset scope is operator
  input. Which BES Cyber Systems exist and at what impact rating is not
  derivable from any document in the corpus."* That claim held across four
  prior tasks (`[GATE]` in T3, carried forward through T4 and the
  completeness correction) and was false the moment the operator's own CIP
  policies entered the corpus: CIP-002 R1 *requires* the entity to identify
  and categorize its BES Cyber Systems, and every CIP policy states its
  applicability in exactly the language `parse_applicable_systems` was
  already written to read. `AssetScope.declared_by` existed in the dataclass
  from T3 onward — nobody had populated it.
- **Description**: `scope_derive.derive_scope()` now unions impact ratings
  and associated-system types across every ingested span containing an
  explicit impact-rating statement, populates `declared_by="derived:corpus"`,
  and files an `applicability_scope` review-queue item with the citing
  evidence (25 spans max, confidence weighted by evidence count). Verified
  live against the operator's real CIP-007 + CIP-003 corpus: 143 citing spans
  produced `impact_present={high, medium, low}` with full evidence, no
  operator prompt required.
- **What stayed a genuine judgement call, not a gate**: `has_erc` and
  `has_control_center` default to the inclusive `True` (matching
  `AssetScope()`'s own default) rather than being derived from a negative
  search — deriving a *false* (excluding a scope dimension) from the mere
  absence of a corroborating span would reproduce the exact false-exclusion
  risk this phase was written to prevent, just moved one level down. The
  queue item names this explicitly so an operator can correct it.

## Why

The applicability gate was carried forward unexamined across three follow-on
tasks because "operator input" reads as a reasonable, conservative default —
it is the same shape as a genuine gate, so nothing forced a re-check. The
lesson generalizes past this one field: **before declaring something operator
input, check whether the operator's own documents already answer it.** A gate
that never gets re-examined is functionally a permanent block, and this one
sat behind four tasks despite the parser to close it having existed the whole
time.
