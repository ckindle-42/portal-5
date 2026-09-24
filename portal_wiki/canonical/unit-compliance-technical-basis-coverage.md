---
id: unit-compliance-technical-basis-coverage
kind: what
title: "Technical basis coverage — counted per requirement, every gap named with its reason"
sources:
- type: code
  path: scripts/compliance/verify_technical_basis_coverage.py
claims: []
confidence: high
tags:
- compliance
- technical-basis
created_at: 1789238000.0
updated_at: 1789238000.0
---

# Technical basis coverage

`verify_technical_basis_coverage.py` is the census half of the two-layers rule:
a requirement should carry what it says (the normative text) and how it is meant
to be met (the Guidelines and Technical Basis, or the separate Technical
Rationale). The script counts, per register standard, how many register nodes
are joined to guidance (`requirement_sections` with relation `technical_basis`,
either anchor method), lists every node still without it, and attaches the
rationale document's own heading list — the evidence an auditor needs to decide
whether a gap is a genuine absence by the drafting team or a join this module
failed to make.

It complements `capture_technical_basis.py` (which captures and places) and
`requirement_anchor.anchor_standard_attachment_gtb` (the heading route that
closed the CIP-002-5.1a and CIP-003-8 locate misses). A coverage number without
per-requirement reasons invites exactly the wrong repair: re-running the
placement to make the number move.

## Why

MODULE_COMPLETE_V1 §P0.5 requires every register requirement to carry its
technical basis wherever one exists, with coverage counted per standard and
every gap named with its reason. A bare fraction (5/44) cannot distinguish
"the drafting team wrote no rationale for this requirement" from "the rationale
exists and the normaliser missed it" — and those two have opposite repairs.
CIP-003-9 is the worked example: its Technical Rationale genuinely covers only
the changed Attachment 1 Section 6, and the receipt proves that from the
document's own headings rather than asserting it.
