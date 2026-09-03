---
id: unit-known-limitations-cip-register-behind-published-versions
kind: what
title: "KNOWN_LIMITATIONS — CIP register version divergence and its coverage shortfall"
sources:
- type: code
  path: portal/modules/compliance/core/cip_register.py
- type: code
  path: portal/modules/compliance/core/currency.py
- type: code
  path: portal/modules/compliance/data/nerc_cip_register.json
claims: []
confidence: high
tags:
- docs
- verified-v1
---

### CIP register — version divergence, Attachment-part shortfall, newer versions published

- **ID**: T3-COMPLIANCE-REG-001
- **Status**: OPEN (documented). The engine flags all three below rather than
  serving stale data silently; closing them is future work.
- **Description**:
  1. **Register vs the old map (RESOLVED 2026-09-03).** The pre-existing
     `nerc_cip_map.json` was 27 R-level entries with *paraphrased* titles, no
     requirement text, and pinned to **CIP-003-8 / CIP-012-1** — the superseded
     versions — while the corpus manifest already held cip-003-9 / cip-012-2. The
     `auto-compliance` persona was instructed to treat CIP-003-9 R1 Part 1.2.6
     gaps as Priority-1 against a register on the wrong version. This stood
     because there were two disagreeing sources of truth and no test comparing
     them. Fixed: the register is now derived, verbatim, Part-level, on the
     enforceable versions; `nerc_cip_map.json` is a generated view of it.
  2. **Attachment / prose parts not extracted.** CIP-002, CIP-003, CIP-012,
     CIP-013 carry their obligations in Attachment 1 or prose sub-sections, not
     the `Table R<n>` format the extractor reads. The register has R-level
     verbatim text for these (15 requirements) but **0 of their ~20 Attachment
     parts**. A coverage matrix over these standards is R-level only. CIP-014's
     R3 lead-in is fragmented in the PDF text and is missed.
  3. **Newer versions are already published.** The Phase 8 currency probe
     (`nerc_cip_currency`) finds that **12 of 13** held standards have a newer
     version PDF live on nerc.com (CIP-002-7, CIP-003-10, CIP-004-8, …,
     CIP-011-4, CIP-013-3). These are adopted-but-not-necessarily-effective; the
     standard PDFs defer their enforcement date to a separate Implementation
     Plan, so the engine reports "verify the enforcement date" and never infers
     one. The register should be rebuilt on whichever versions are enforceable
     once those dates are confirmed against NERC's schedule.

## Why

Recording this keeps the honest position visible: the register is a real
improvement over a paraphrased map on superseded versions, but it is not
complete (Attachment parts) and not guaranteed current (a newer published wave
exists). Each shortfall is surfaced by a test or a probe rather than hidden —
which is the point of building currency as a prerequisite rather than a
follow-on.
