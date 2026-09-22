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
  path: scripts/compliance/closeout_family_sweep.py
- type: code
  path: scripts/compliance/write_closeout_report.py
- type: code
  path: scripts/compliance/bench_sweep_engines.py
- type: code
  path: scripts/compliance/decide_sweep_engine.py
- type: code
  path: scripts/compliance/ask_product_questions.py
  commit: 29665293
- type: code
  path: scripts/compliance/adjudicate_determinations.py
- type: code
  path: scripts/compliance/diagnose_dead_standards.py
- type: code
  path: scripts/compliance/single_vs_split.py
- type: code
  path: scripts/compliance/family_links.py
- type: code
  path: scripts/compliance/ask_conversational.py
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

TASK_COMPLIANCE_PROVE_THE_MODULE_V1 adds two more instruments in the same
spirit. `adjudicate_determinations` replaces `agreement()`'s n=11 as the
module's quality number: `--extract` walks every reading-derived
`relationship_assertions` row into a judgeable unit (requirement text,
operator section text, relation, cited sentence), and `--fold` takes the
coding agent's own verdicts on those units and computes precision overall
and per standard — the adjudication is a human-equivalent read, not a
mechanical rule, and the script writes nothing to the store either way.
`diagnose_dead_standards` classifies every Part-level requirement in a
named standard into one of four mechanical causes (no_operator_document,
below_threshold, empty_population, reading_failure) from the store's own
autosync links payload, `requirement_scope.population`, and the existing
refusal adjudication — never a new threshold, and it does not touch
`DEFAULT_THRESHOLD`. `single_vs_split` (§P4b) runs the same five-turn
conversation three ways — the incumbent split (gemma4, through the
deployed router) and two single-seat splash arms (Qwen3.8-27B,
Qwen3.6-35B-A3B, called directly against the splash forwarder since it has
no `config/backends.yaml` entry) — reusing the router's own
`_dispatch_tool_call` so a splash arm's tool loop is authorized exactly
the way the deployed one is.

LOAD_AND_CONVERSE_V1 adds two instruments in the same spirit.
`family_links` (§P3.2) runs `build_links` for every register standard
revision — not only the standards a past campaign or an autosync lifecycle
change touched — against the whole projected operator corpus, and persists
per-requirement absence (`requirement_absence`) where it is computed, so a
census can distinguish *searched and found nothing* from *never searched*.
`ask_conversational` (§P4) asks fourteen questions that name no requirement
address at all, on the deployed workspace, and passes a question only when
it answers, `compliance_search` was ACTUALLY called (router counters), every
citation resolves, and both sides are cited — with the absence questions
inverted: honest absence passes, invented coverage fails, judged by the
module's own assertion classifier against the store's recorded edges.
