---
id: unit-agent-loop-record-path-writing-enabled-ci-gated
kind: what
title: "AGENT_LOOP \u2014 Record path (writing enabled, CI-gated)"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Record path (writing enabled, CI-gated)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.506429
updated_at: 1784946220.506429
---

`agent.writeback.record_outcome(...)` proposes a cited unit into
`portal_wiki/proposed/` via `portal.platform.wiki.writeback.propose_unit`.
Promotion is the gate: `confirm_unit` / `reject_unit`. Nothing auto-merges.
