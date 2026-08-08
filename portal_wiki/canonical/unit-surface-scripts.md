---
id: unit-surface-scripts
kind: mixed
title: "Operator script farm \u2014 standalone tools for bench, lab, media, and provisioning"
sources:
- type: code
  path: scripts/*.py
- type: code
  path: scripts/lib/*.py
- type: code
  path: scripts/validation/*.py
last_generated_commit: 59839264613bae9f5c35a66902c8cc274654191d
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785883000.0
updated_at: 1785883000.0
---

The `scripts/` tree is the operator tool farm: standalone executables run from
the repo root. Each tool reads live state from config, the lab, or its target
services, printing findings and exiting with a status code. Families: bench
and eval harnesses, corpus and lab provisioning, media generation, host-native
servers, Open WebUI provisioning, Grafana updaters, and infra and quality
gates. Corpus injection is a three-lane contract: pre-indexed BOTS buckets on
the Splunk host, curated datasets through the ingest path, and on-demand
Caldera activity on lab targets.

## Why

Operator work here is heterogeneous and mostly one-shot — a bench run, a
corpus ingest, a Grafana push, a lab reconciliation. A shared framework would
couple unrelated workflows, so the standalone contract keeps each tool
independent and directly invokable by an operator or agent.

## Interfaces

Tools run from the repo root against the same sources of truth:
`config/portal.yaml`, `config/backends.yaml`, `.env`, and the live services.
Output is stdout plus a nonzero exit. Safety modes recur: `--dry-run` before
writes, skip-heavy and update selectors, and input selection for the Grafana
writers. CLI-coding shims launch stock or Portal Claude Code and opencode
modes without touching repo config.

## Gotchas

No runner exists, so run each tool with the environment it expects; output is
current reality, not a record. Bench runs are gated by `execute_preflight`,
not doc-baked counts; corpus injection is reviewed dry-run first; matrix
analyzers like `blend_acceptance_results` merge evidence without a verdict;
supervisor recovery is bounded to `ALLOWED_ACTIONS`.
