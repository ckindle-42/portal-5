---
id: unit-toolpreselect-scenario-gen
kind: mixed
title: "Tool-preselect scenario generator \u2014 exhaustive adversarial corpus"
sources:
- type: code
  path: tests/toolpreselect/scenario_gen.py
  commit: 7c9c4031
last_generated_commit: 7c9c4031
claims: []
confidence: high
tags:
- authored-v1
- tests
- toolpreselect
created_at: 1785795861.42414
updated_at: 1785795861.42414
---

`scenario_gen.py` generates the exhaustive acceptance corpus for the tool
preselector: it reads the *live* tool inventory from `tool_registry.refresh()`
and builds positive scenarios (one clean task per tool), decoys for about a
fifth of tools, compound ambiguous cases, reorder checks (the same positives
with the tool list reversed), and no-good-fit prompts. The output is
`tests/toolpreselect/scenarios.json`.

## Why

A preselector that returns the wrong tool for a clear task, or returns the
same tool regardless of order, is a silent correctness failure — and the only
way to prove it works is a corpus that deliberately attacks its failure
modes. The decoy, compound, reorder, and no-good-fit families exist because a
naive scorer passes the clean positives while missing exactly the cases that
matter in real use: an ambiguous request, a tool list that should change the
answer, and a request nothing fits. Deriving the positives from the live
registry rather than a frozen list keeps the corpus honest as the tool
inventory grows — a new tool gets a scenario without the generator being
re-edited by hand.

## Interfaces

`_build_positive_scenarios`, `_build_decoy_scenarios`,
`_build_compound_scenarios`, `_build_reorder_scenarios`, and
`_build_no_good_fit_scenarios` are the family builders; `generate_scenarios`
coordinates them and `main` writes the JSON.

## Gotchas

Tools not in the hand-crafted per-category table get a generic-but-realistic
scenario derived from their description (`_FALLBACK_SCENARIOS`) — so coverage
of the registry is exhaustive even where the hand-crafted prompts have not
been written for a specific tool.
