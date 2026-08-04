---
id: unit-security-investigation-surface
kind: mixed
title: "Security investigation surface \u2014 evidence + case notebook"
sources:
- type: code
  path: portal/modules/security/core/investigation/__init__.py
  commit: 573a2377
last_generated_commit: 573a2377
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- investigation
created_at: 1785796309.4335308
updated_at: 1785796309.4335308
---

The investigation subpackage is the RBP engine's investigation layer —
agents, evidence, and the case notebook. It is the Phase 6 surface of the
security build program, re-exporting the evidence record/store and the case
notebook so the engagement layer can build investigations from them.

## Why

The three pieces — evidence, notebook, and the bench that measures them —
share one conceptual boundary: everything an agent concludes during an
investigation must be traceable to evidence, and the evidence is immutable.
Grouping them under one package with a stable re-export surface is what lets
the engagement machinery import `EvidenceStore` and `CaseNotebook` without
reaching into each module's internals, and it marks where a new investigation
component (an agent loop, a timeline) belongs.

## Interfaces

`EvidenceRecord`, `EvidenceStore`, `SourceAuthority`, and `new_evidence_id`
come from `evidence`; `CaseNotebook` from `case_notebook`. `__all__` pins the
public surface.
