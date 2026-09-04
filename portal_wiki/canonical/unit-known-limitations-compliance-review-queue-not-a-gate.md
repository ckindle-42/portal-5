---
id: unit-known-limitations-compliance-review-queue-not-a-gate
kind: what
title: "KNOWN_LIMITATIONS — a queue is not a gate"
sources:
- type: code
  path: portal/modules/compliance/core/review_queue.py
- type: code
  path: portal/modules/compliance/core/mapping_store.py
claims: []
confidence: high
tags:
- docs
- verified-v1
---
### A queue is not a gate

- **ID**: T5-COMPLIANCE-LANDING-003
- **Status**: LANDED `TASK_COMPLIANCE_ENGINE_LANDING_V1` Phase 1, live-verified
  Phase 6. Replaces the pattern of four would-be `[GATE]`s (asset scope,
  document tier, mapping approval, tier conflict) that would otherwise have
  blocked execution on an operator answer.
- **Description**: `review_queue.py` is LanceDB-backed
  (`compliance_review_queue`), five kinds (`applicability_scope`,
  `document_tier`, `compliance_conflict`, `mapping_proposal`,
  `low_confidence_extraction`), four statuses
  (`OPEN`/`CONFIRMED`/`REJECTED`/`SUPERSEDED`). Two rules make it a queue and
  not a gate: (1) an OPEN item never blocks — `compliance_gaps` runs on the
  derived scope and derived tiers regardless of whether anything is
  confirmed; (2) every output resting on an open item names the item id
  (`open_queue_items` on a `compliance_gaps` row, `scope.queue_item_id` on
  every response). A decision is reversible: `decide()` writes a **new** row
  with `prior_item_id` pointing at the one it closes; the prior row's status
  flips to `SUPERSEDED` in place — its value is never rewritten, mirroring
  `mapping_store`'s `valid_to` closure discipline. `sync_proposed_mappings()`
  wires `mapping_store`'s existing `approved_by == ""` proposals into the
  queue rather than building a second path, per the task's explicit
  anti-pattern.
- **Verified against a real security-review finding, not just a design
  review**: an automated review during this task flagged that `decide()`'s
  `item_id` reached a string-interpolated LanceDB filter
  (`tbl.delete(f"id = '{item_id}'")`) from `compliance_review_decide`, an MCP
  tool taking arbitrary caller input — a real filter-injection path, not a
  theoretical one. Fixed with an id-shape guard (`_ID_RE`) before the
  f-string; verified a `' OR '1'='1` payload is rejected with `ValueError`
  rather than reaching the filter.

## Why

A gate stops the system until a person answers; a queue lets the system keep
answering with its best evidence while the person catches up on their own
schedule — the difference is not cosmetic; it is what actually got this
program shipped after four tasks stalled on gates. The reversibility
discipline (append, never overwrite) is what makes "proceed anyway" honest
rather than reckless: every derived answer is traceable to exactly which
judgement it rested on, and correcting that judgement later does not erase
the record of what the system said before the correction.
