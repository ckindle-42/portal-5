---
id: unit-agent-loop-record-path-writing-enabled-ci-gated
kind: what
title: "AGENT_LOOP \u2014 Record path (writing enabled, CI-gated)"
sources:
- type: code
  path: portal/platform/agent/writeback.py
- type: code
  path: portal/platform/wiki/writeback.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.506429
updated_at: 1784946220.506429
---

`agent.writeback.record_outcome(...)` is the loop's write path: it distills an
outcome into a cited unit and proposes it via
`portal.platform.wiki.writeback.propose_unit`, landing in
`portal_wiki/proposed/` with status `proposed`. Promotion is the gate —
`confirm_unit` / `reject_unit` in the same module decide whether a proposal
reaches canon. Nothing the agent loop proposes auto-merges:
`record_outcome` never passes `auto_confirm`, and a failed writeback returns
`None` rather than blocking the loop.

## Why

The record path is separated from the loop so that learning is confirm-gated
and provenance-required. A loop that could write straight into the canonical
wiki would certify its own outcomes; staging proposals first means every unit
passes through a human gate, and the `sources` requirement in `propose_unit`
forces a loop to cite real evidence before its learning can be recorded.
