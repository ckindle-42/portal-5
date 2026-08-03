---
id: unit-security-eval-ablation-attribution
kind: mixed
title: "Ablation attribution \u2014 multi-state failure attribution instrument"
sources:
- type: code
  path: portal/modules/security/eval/ablation_attribution.py
  commit: 1d62c01d
last_generated_commit: 1d62c01d
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- eval
created_at: 1785795981.801562
updated_at: 1785795981.801562
---

`ablation_attribution.py` is the failure-attribution instrument for
blue-orchestration ablation runs. Its central discipline is that the primary
outcome label is *not* enough: every record carries independent completion,
retrieval-observation, and Hunter-citation states plus secondary failures, so
that co-occurring failures are not falsely attributed to one cause by branch
order. It is hermetic — it operates on persisted plain dicts and makes no
live calls.

## Why

The whole point of the ablation is to learn *why* an arm failed, and the
label alone cannot say that. `ATTENTION_LOSS` exists to separate "telemetry
was retrieved but the Hunter did not cite it" from a retrieval failure, and
`ATTRIBUTION_UNKNOWN` is mandatory for legacy traces that never persisted the
retrieved payload — because the absence of evidence is not evidence of
absence, and forcing a legacy trace into a causal class would be fabrication.
`_decide_route` uses the Wilson lower bound on the dominant outcome to decide
whether an arm's edge is statistically stable or still non-convergent, so a
routing decision is not made on one lucky run.

## Interfaces

`classify` produces an `ArmScenarioOutcome` per (arm, scenario) with the
primary label and the independent observation states; `summarize` aggregates
into an `ArmSummary`; `decide_route` returns the routing decision from the
aggregate; `_wilson_lower` and `_stable_dominant` are the statistics behind it.

## Gotchas

The module's docstring is explicit that fixture coverage establishes
implementation behaviour only — it is not evidence the instrument is valid on
live traces. The attribution schema is versioned (`ATTRIBUTION_SCHEMA_VERSION`)
so a scorer change is tracked, not silently applied to old results.
