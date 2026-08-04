---
id: unit-known-issues-known-issues
kind: what
title: "KNOWN_ISSUES \u2014 Known Issues"
sources:
- type: code
  path: portal/platform/wiki/render.py
- type: code
  path: portal_wiki/canonical/unit-known-limitations-known-limitations.md
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.507908
updated_at: 1784946220.507908
---

# Known Issues

`KNOWN_ISSUES.md` is intentionally empty by design. Architectural
constraints and accepted tradeoffs are documented in the canonical
limitation register — the `unit-known-limitations-*` units rendered into
`KNOWN_LIMITATIONS.md` by `portal/platform/wiki/render.py`
(`render_all_generated_blocks`) — and entries there are accepted
tradeoffs, not bugs to fix. A genuine operational bug belongs in the
issue tracker at https://github.com/ckindle-42/portal-5/issues rather
than in this file, keeping defects separate from decisions.

`KNOWN_ISSUES.md` is itself a Tier-1 doc whose block is rendered from this
unit, so the "intentionally empty" statement is the single authored
source for that page.

## Why

An empty known-issues page is a deliberate signal, not an omission:
a limitations register already exists, and duplicating its contents here
would create a second copy that drifts as the register changes. Keeping
genuine defects in the issue tracker instead separates bugs (which are
fixable and should be filed) from accepted design tradeoffs (which
`KNOWN_LIMITATIONS.md` records with their status), so an operator reading
the limitations page is never misled into treating a recorded decision as
an open defect. This unit is grounded to the renderer that produces the
page and to the limitation units that supply its substance.
