---
id: unit-surface-sec-bully
kind: mixed
title: "Defensive Bully review and data-plane modules"
sources:
- type: code
  path: portal/modules/security/core/bully/*.py
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- bully
created_at: 1786751207.0
updated_at: 1786751207.0
---

`portal.modules.security.core.bully` contains the retained Bully review, intake, data-plane, corpus, discovery, and evaluation modules. The former autonomous hunt CLI and orchestrator were removed during consolidation; this page describes the code that remains and does not claim an end-to-end hunt product path.

## Why

The retained code groups evidence and corpus handling, field-role inference, observed-event intake, discovery and cousin evaluation, measurement, live data-plane connectors, and review artifacts. The module glob tracks the present source tree; historical phase labels and previously described iteration stages are not current interfaces.

## Interfaces

The retained boundaries are the exported package symbols and the functions documented by each module. `data_plane.py` and `live_connect.py` provide data-plane code; `field_roles.py`, `artifact_graph.py`, and the unit evaluation modules cover intake and measurement; `discovery_bench.py`, `cousin_engine.py`, and `embedding_spaces.py` cover retained discovery evaluation. Review routes and their receipts are documented by the review subsystem, not by a retired hunt loop.

## Gotchas

Tests for retained behavior live in `tests/security/bully/` and alongside the security modules. Benchmarks and live connector paths have separate evidence requirements; a passing unit or integration test does not establish a live operator run.
