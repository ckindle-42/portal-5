---
id: unit-tests-scripts-capability-probe
kind: mixed
title: "Coding capability probe \u2014 execution-validated 7-dimension matrix"
sources:
- type: code
  path: tests/scripts/capability_probe.py
  commit: dc13b2d5
last_generated_commit: dc13b2d5
claims: []
confidence: high
tags:
- authored-v1
- tests
- scripts
- bench
created_at: 1785796162.060698
updated_at: 1785796162.060698
---

The coding capability probe drives each candidate model through the pipeline
across seven capability dimensions, and for execution-tested scenarios it
actually validates the model's output: it extracts the emitted code, appends
the hidden test harness, runs it in the sandbox MCP, and scores a pass only
when the exit code is zero *and* the expected stdout appears. The output is a
comparative matrix with no verdict — promotions stay operator-only.

## Why

A probe that only asked a model to *describe* a capability would be measuring
rhetoric, not ability. The execution-validation step is what makes the matrix
meaningful: code that compiles and produces the expected output is evidence
in a way a self-assessment never is. Network scenarios are the one carve-out —
they need the sandbox started with `SANDBOX_ALLOW_NETWORK=true` because the
default sandbox has no network, and that is an operator decision made before
the run, not something the probe silently widens. The no-verdict contract is
the same one every bench artifact follows: the matrix is the deliverable, and
promotion is a human decision (the PROMOTE_POLICY split).

## Interfaces

`main` reads the scenario YAML and model list, drives each model through its
bench workspace via the pipeline, runs the execution-testing path through the
sandbox, and writes the comparative matrix markdown. The network flag is
respected per scenario so a run does not silently fail network-gated cases.

## Gotchas

The probe scores PASS on the strict conjunction (exit 0 AND expected output) —
a model that runs cleanly but prints the wrong thing is a fail, which is
stricter than a human eyeballing the transcript might be.
