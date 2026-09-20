---
id: unit-surface-compliance-closeout-scripts
kind: mixed
title: "Compliance closeout scripts — the CLOSEOUT_V1 evidence instruments"
sources:
- type: code
  path: scripts/compliance/verify_conjunction_adoption.py
  commit: 29665293
- type: code
  path: scripts/compliance/calibrate_cip007.py
  commit: 29665293
- type: code
  path: scripts/compliance/adjudicate_refusals.py
  commit: 29665293
- type: code
  path: scripts/compliance/ask_product_questions.py
  commit: 29665293
claims: []
confidence: high
tags:
- authored-v1
- surface
- compliance
- closeout
created_at: 1789945809.999774
updated_at: 1789945809.999774
---

The closeout's instruments, one per phase of CLOSEOUT_V1, each reporting and
never acting on its own judgment. `verify_conjunction_adoption` diffs the
six-case before/after sets around the adopted conjunction sentence and halts
on any PASS-to-FAIL regression; its verdicts are a stated mechanical floor,
because the experiment's cells carry no verdict field and a field-probe would
pass trivially. `calibrate_cip007` sorts CIP-007-6's store pairings against
the PROVE_THEN_SCALE baseline into preserved / changed-relation / lost / new —
a comparison, never an auto-reconciler.

## Why

The module's history records seven abandoned live harnesses; the close reuses
the mature one and adds only recording instruments whose every receipt carries
a verdict and a reason, so a close that outran its evidence cannot recur. The
adjudication classifies refusals into the three A6.3 categories without
admitting anything — checker_strictness is a candidate set for its own future
task, not a backlog of edges waiting to be let in.

## Interfaces

`ask_product_questions` is the gate: it asks the three product questions on
the deployed `compliance-reading` workspace through the configured router,
one conversation per question, and passes a question only when the answer is
non-empty, every cited section id resolves in the store, and at least one
resolved citation sits on the side the question requires (operator for
coverage and exceedance, regulatory for unused latitude).
