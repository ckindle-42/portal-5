---
id: unit-surface-investigation
kind: mixed
title: "Security investigation subpackage \u2014 immutable evidence and notebook"
sources:
- type: code
  path: portal/modules/security/core/investigation/*.py
last_generated_commit: 22007054d6cba73357ea3c5d7d7c97f5c252d7dc
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- investigation
created_at: 1785884400.0
updated_at: 1785884400.0
---

The investigation subpackage is the investigation layer of the RBP engine: the immutable evidence store, the per-case case notebook, and the honesty bench. Every tool call during an engagement produces one `EvidenceRecord` in the append-only `EvidenceStore`, graded by `SourceAuthority` so reasoning can weight source trust separately from content.

## Why

The pieces share one discipline: nothing an agent concludes may outlive the evidence behind it, so evidence is immutable and notebook mutations are recorded, never destructive. Promotion to the prior-incident library is analyst-confirm-only, so a case conclusion never silently becomes institutional knowledge. The multi-agent stack must beat a single-agent baseline on all three metrics, or the honest move is to simplify back toward baseline.

## Interfaces

The public surface is pinned by `__all__` in the package init: `EvidenceStore`, `EvidenceRecord`, `SourceAuthority`, and `new_evidence_id` from evidence, `CaseNotebook` from the notebook. The bench exposes `run_comparison`, `run_benchmark`, and the metric functions `compute_hallucination_rate`, `compute_contradiction_detection_rate`, and `compute_evidence_completeness`.

## Gotchas

The authority ladder is deliberately coarse — a low-authority record is never treated as strong just because its content looks credible, and the bench only means anything when planted contradictions are genuinely hard. Every notebook query is scoped by `case_id`, so one case can never read another's memory.
