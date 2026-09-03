---
id: unit-known-limitations-compliance-implicit-change-recall
kind: what
title: "KNOWN_LIMITATIONS — CIP change pipeline implicit-change recall ceiling"
sources:
- type: code
  path: portal/modules/compliance/core/register_diff.py
- type: code
  path: portal/modules/compliance/core/change_pipeline.py
- type: code
  path: portal/modules/compliance/data/nerc_cip_register.json
claims: []
confidence: high
tags:
- docs
- verified-v1
---
### CIP change pipeline — implicit-change detection recall ceiling

- **ID**: T4-COMPLIANCE-CHANGE-001
- **Status**: OPEN (documented). Phase 3 verification publishes false-negative
  and unmatched counts separately and does not assume the implementation plan is
  exhaustive; the rollup states the recall figure plainly.
- **Description**: The change pipeline
  ([[unit-compliance-change-pipeline]]) detects a Part-level change only where it
  is visible **in the register** — the verbatim requirement text, applicable-systems
  column, measure text or VRF differs between two versions, or a Part id
  appears/disappears. One class escapes it:
  1. ~~**Attachment / prose obligations.**~~ **RESOLVED 2026-09-03**
     (TASK_CIP_REGISTER_COMPLETENESS_V1). Attachment 1 sections and prose
     part-lists are now register Parts, so a new section like CIP-003-9's
     Section 6 (vendor electronic remote access) is raised as `PART_ADDED`.
     `T3-COMPLIANCE-REG-001` item 2 is closed; diff-false-negatives vs the T4
     ground truth: 1 → 0.
  2. **Implicit change with no textual delta.** Wording whose *meaning* shifted
     through a defined-term redefinition, a moved cross-reference, or an
     implementation-plan clarification, with the Part text itself unchanged.
     Comparable published work on versioned-document QA reports ~60% recall on
     this class; the pipeline is bounded by the same ceiling and is **not**
     measured as exhaustive.
- **Verified transition**: `CIP-003-8 → CIP-003-9` (re-run P4) — 22 rows,
  6 substantive: the new 1.2.6 wording, the 1.2.6→1.2.7 renumber, **and
  Attachment 1 Section 6 + 6.1–6.3 as `PART_ADDED`**. See
  `reports/compliance/REGISTER_COMPLETENESS_V1.md` (supersedes the
  `CHANGE_PIPELINE_V1.md` figures).

## Why

Stating this ceiling is the difference between a tool an SME can calibrate
against and one they will eventually trust past its evidence. The failure mode
this whole subsystem exists to prevent is a silently stale policy; a diff engine
that over-claims its own completeness reintroduces exactly that risk one level up.
Nobody should read a clean diff as proof that nothing material changed — only
that nothing changed in the register's extracted surface.
