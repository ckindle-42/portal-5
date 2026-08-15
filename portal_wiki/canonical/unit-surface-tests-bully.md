---
id: unit-surface-tests-bully
kind: mixed
title: "Defensive Bully integration test lane"
sources:
- type: code
  path: tests/security/bully/*.py
last_generated_commit: 6a4b4d26
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- bully
- tests
created_at: 1786751207.0
updated_at: 1786751207.0
---

`tests/security/bully/` holds the Defensive Bully integration test lanes -- P1's boundary/import-scan tests, end-to-end LOOP-iteration tests, and later phases' council/gate/handoff integration tests -- as distinct from the package's own hermetic unit tests, which live alongside `portal/modules/security/tests/` per the existing security test surface (`unit-surface-sec-tests`).

## Why

`FINAL_VALIDATION_DEFENSIVE_BULLY.md`'s conventions split hermetic unit tests (existing security test surface) from integration lanes that exercise more than one bully module together (this directory) -- the same tree shape `FINAL_ARCHITECTURE_DEFENSIVE_BULLY.md` SS1 declares for the package itself.

## Interfaces

Test modules only; no runtime code. Imports `portal.modules.security.core.bully.*` and `portal.modules.security.core.commands.hunt_modes`.

## Gotchas

Hermetic per the project testing rules: `tmp_path` for any I/O, mocked `httpx`, no network/lab/Splunk/Ollama. Live/operator-invoked behavioral proofs (FINAL_VALIDATION SS3) are out of scope for this lane.
