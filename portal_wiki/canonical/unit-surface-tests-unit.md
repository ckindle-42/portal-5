---
id: unit-surface-tests-unit
kind: mixed
title: "Platform unit-test suite \u2014 hermetic contract pins for routing, config,\
  \ fleet, and wiki"
sources:
- type: code
  path: tests/unit/*.py
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- authored-v1
- tests
- unit
created_at: 1785882400.0
updated_at: 1785882400.0
---

The platform unit-test suite in `tests/unit/*.py` is the hermetic contract layer under the routing, config, fleet, and wiki subsystems, proving decision logic with mocked HTTP and subprocesses, no live backends, no Docker, and `tmp_path` file I/O, verifiable without Ollama, Open WebUI, or the fleet.

## Why

The suite's hermetic rule is load-bearing: a test reaching a real backend fails in CI. Deterministic logic — recall scoring, capability extraction, transcription — is verified before model-dependent layers are trusted. `sync-config` idempotence is asserted as the freshness gate, the sandbox's default-off posture degrades to safe on misconfiguration, and write-back provenance plus the confirm gate protect what enters canonical.

## Interfaces

Pins routing and dispatch (intent classifier with keyword fallback, hint validation, expected-model resolution, module toggle, registry health hysteresis), backend health and load control (semaphores, concurrency slots, tool backoff, registry-refresh carry-forward), config single-source (schema, pre-gate validation, artifact idempotence, catalog parity, Ollama URL canonicalisation), the MCP fleet (single-source ids and ports, import-time vendor smoke, endpoint shapes), wiki platform gates (core schema and store, quality gate, spine gates, provenance ledger, writebacks, search ranking), evaluation and persona matrix (catalog schema, quality signals, promptfoo validation, council determinism), bench machinery (TPS probe, skip semantics, supervisor detection, capability scoring), channels and notifications, streaming and telemetry (SSE golden frames, state persistence), shared workspace and sandbox security (traversal guard, network default-off, lab-exec posture), and UAT and acceptance helpers (dispatch, grading, metrics URL).

## Gotchas

The suite must run offline; reaching a real backend, Open WebUI, or Docker fails CI. File I/O goes through `tmp_path`, and streaming-path changes need the live `smoke_stream.sh` gate, which mocks cannot replace.
