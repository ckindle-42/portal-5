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
claims:
- probe: compliance.completeness
  contains: "completeness_holes:0"
- probe: compliance.completeness
  contains: "denominator_self_derived:False"
- probe: compliance.completeness
  contains: "fidelity_failed:0"
confidence: high
tags:
- docs
- verified-v1
---

### CIP register — version divergence, Attachment-part shortfall, newer versions published

- **ID**: T3-COMPLIANCE-REG-001
- **Status**: items 1 and 2 RESOLVED; item 3 OPEN (documented). The engine
  flags what remains rather than serving stale data silently.
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
  2. **Attachment / prose parts not extracted (RESOLVED 2026-09-03,
     TASK_CIP_REGISTER_COMPLETENESS_V1).** CIP-002/003/012/013/014 carry
     obligations in Attachment 1 or a colon-terminated prose list, not the
     `Table R<n>` the extractor read. The register held R-level text for these
     and **0 Parts**, yet `n_missing` reported **0** — because it was a fidelity
     round-trip over the extractor's own output, not a completeness check
     (**the denominator was the numerator**). Fixed: `_prose_list_parts` +
     `_cip002_attachment1` + `_cip003_attachment1` (register 152 → 254 nodes,
     130 → 232 Parts); `assess_completeness` is a separate, document-derived
     metric (colon-lead-in with no children; the document naming its own
     children; numbering gaps) that never derives its denominator from the
     extractor. `denominator_source` per standard is asserted never
     `"extractor"`. **General lesson: a completeness metric computed by
     iterating what you found is a fidelity metric.**
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
