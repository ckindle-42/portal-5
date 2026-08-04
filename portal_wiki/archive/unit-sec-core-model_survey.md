---
id: unit-sec-core-model_survey
kind: mixed
title: "Model survey \u2014 model behaviour inventory"
sources:
- type: code
  path: portal/modules/security/core/model_survey.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902839
updated_at: 1785800295.902839
---

The model-survey harness that probes candidate models' behaviours (refusal, tool-calling, capability) to inventory what each model can and cannot do.

## Why

A model inventory is the ground truth for model selection: knowing which models refuse what, call tools reliably, and deliver which capabilities is what the fleet decisions are made on. The survey produces that inventory systematically.

## Interfaces

The model-survey harness that probes candidate models' behaviours (refusal, tool-calling, capability) to inventory what each model can and cannot do lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
