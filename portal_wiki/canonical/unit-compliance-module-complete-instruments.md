---
id: unit-compliance-module-complete-instruments
kind: what
title: "MODULE_COMPLETE_V1 campaign instruments — re-type, sessions, correction loop"
sources:
- type: code
  path: scripts/compliance/retype_relations.py
- type: code
  path: scripts/compliance/session_proof.py
- type: code
  path: scripts/compliance/correction_loop_demo.py
claims: []
confidence: high
tags:
- compliance
- campaign
- module-complete
created_at: 1789239000.0
updated_at: 1789239000.0
---

# MODULE_COMPLETE_V1 campaign instruments

Three campaign scripts, one per seam the MODULE_COMPLETE_V1 task closes.

`retype_relations.py` acts on adjudicated wrong relations: it REVOKES an edge
the adjudicator marked `WRONG_RELATION` (review_state REVOKED, the deciding
reason written onto the row) and writes the corrected relation as its own
determination carrying the SAME citation — the re-type changes the relation,
not the reading it rests on. Nothing is deleted; the revoked original remains.
Revoked edges drop out of populations (`linked_internal` reads only
approved/proposed), so a later sweep cannot re-affirm what adjudication
removed.

`session_proof.py` runs the multi-turn proof: sessions of five turns over ONE
`WorkspaceThread` each — retrieval, a referential follow-up, a narrowing, a
cross-standard or intent-review turn, and a challenge — grounding every turn
through `ask_conversational._grounding`, the one grounding rule, with prompt
tokens per turn recording where the window bites.

`correction_loop_demo.py` demonstrates the correction loop end to end on the
deployed tool surface: read, disagree, correct, re-read — asserting the
correction is present in the next material AND that the re-read accounts for
it — then exercises `compliance_standing_questions(run=True)` for the first
time.

## Why

MODULE_COMPLETE_V1 names three seams — admission disconnected from
entailment, a conversation that was never a conversation, and a correction
filed under the wrong key — and requires each fix measured by a receipt of its
own. These scripts are those receipts' instruments; the store-correction rule
they encode (supersede, never delete; corrected edges keep the original
citation) is the store's accumulation discipline made operational.
