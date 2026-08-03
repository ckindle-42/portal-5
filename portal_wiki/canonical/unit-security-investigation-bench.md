---
id: unit-security-investigation-bench
kind: mixed
title: "Investigation bench \u2014 single-agent baseline honesty ruler"
sources:
- type: code
  path: portal/modules/security/core/investigation/bench_investigation.py
  commit: 573a2377
last_generated_commit: 573a2377
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- investigation
created_at: 1785796326.5592508
updated_at: 1785796326.5592508
---

`bench_investigation.py` is the investigation benchmark — the honesty ruler
for the multi-agent stack. It builds a single-agent baseline (one model with
all tools) as the null hypothesis, adversarial test cases with planted
contradictions and missing-evidence traps, and three metrics: hallucination
rate, contradiction detection, and evidence completeness.

## Why

The multi-agent investigation stack is expensive complexity, and complexity
must earn its place. The baseline is the yardstick: if the multi-agent
system does not beat the single agent on all three metrics, the honest
conclusion is to simplify back toward baseline rather than ship machinery
that a single model could match. The adversarial cases exist because naive
benchmarks are beaten by naive agents — a hallucination metric without
planted contradictions measures nothing, because a model that just agrees
with everything has no chance to be caught contradicting itself. The three
metrics deliberately split the failure modes: hallucination rate catches
invented findings, contradiction detection catches the model failing to
notice conflicting evidence, and evidence completeness catches the model
stopping early.

## Interfaces

`compute_hallucination_rate`, `compute_contradiction_detection_rate`, and
`compute_evidence_completeness` are the metric functions; `InvestigationScenario`
and `InvestigationResult` are the data shapes; `run_single_agent_baseline`
and `run_multi_agent` are the two runners; `run_comparison` and `run_benchmark`
produce the comparative result.

## Gotchas

The benchmark is only meaningful when the adversarial cases are actually
hard — a planted contradiction that a single model notices trivially makes
the baseline look better than it is, which is the opposite of the ruler's
purpose.
