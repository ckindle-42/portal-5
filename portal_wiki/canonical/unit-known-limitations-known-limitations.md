---
id: unit-known-limitations-known-limitations
kind: what
title: "KNOWN_LIMITATIONS \u2014 Known Limitations"
sources:
- type: code
  path: portal/platform/wiki/render.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.660347
updated_at: 1784946220.660347
---

Canonical limitation register. Each entry carries its own current status: unresolved entries define active constraints, while resolved, retired, or shelved entries preserve the decision and evidence that prevent the same issue from being rediscovered or reintroduced. The status inside an entry is authoritative; presence in this register alone does not mean the issue is open.

`KNOWN_LIMITATIONS.md` is a Tier-1 doc whose blocks are rendered by `portal/platform/wiki/render.py` (`render_all_generated_blocks`): this unit provides the intro paragraph, and each `unit-known-limitations-*` unit provides one section, so the doc stays current as the individual units change without manual editing.

## Why

The register is a rendered view, not an independent ledger, which is the whole point: an operator reads one doc, but every section traces to a unit that can be individually verified and re-grounded against code. Making the status field authoritative per entry keeps resolved issues visible as history while preventing stale entries from being mistaken for open constraints, so a regression cannot quietly reopen a closed problem.
