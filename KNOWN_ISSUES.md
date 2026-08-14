# Known Issues

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

---
