---
id: unit-surface-sec-bully
kind: mixed
title: "Defensive Bully — autonomous purple-team hunt loop package"
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

`bully/` is the additive package for the Defensive Bully purple-team hunt loop: an autonomous cousin-discovery engine layered on top of the existing Red/Blue/Purple bench (`exec_chain.py`, `blue.py`, `episode.py`) without changing their runtime behavior until an explicit cutover phase. It owns its own durable state (`hunt_state.db` under `PORTAL5_HUNT_DIR`, outside the repo) and its own semantic memory projection (a LanceDB hunt-memory projection); it never becomes a second knowledge authority for anything Portal 5 already governs.

## Why

The build program (`coding_task/bully/final/`, `coding_task/bully/tasks/`) phases the work P0-P7; P1 lands the brain substrate — versioned boundary contracts, the SQLite-backed store with hash-chained decision events and a transactional outbox, evidence manifests over the existing Episode truth plane, the ORG knowledge projection with mandatory recall receipts, behavior signatures, the two-axis BR-COUSIN grading engine (shadow dual-run against the legacy `unknown_defense.py` lexical grader), an investigation arm adapting `blue_orchestrate.py`'s section runners, and the LOOP orchestrator that sequences one full hunt iteration end-to-end. Later phases add the alert bin/council gate, red-side mutation and drift, discovery/targeting, handoff/detection-proposal, and the training flywheel — each its own module under this same package, covered by this same surface glob (post-P0 thin-spine contract: one surface entry, no per-file units, no re-stamp tax).

## Interfaces

Module-internal APIs only (never an MCP tool, never a new port): `store.py` is SUB, the sole owner of the hunt-state database; `organ.py` is ORG, the sole toucher of the semantic hunt-memory projection; `cousin_engine.py` is BR-COUSIN, the two-axis relationship/response grading engine for the *provoked* path (parent episode vs mutated child); `cousin_relation.py` is the separate observed-mode grader (`TASK_BULLY_COUSIN_RELATION_V1`) comparing a sparse real arrival against the anchor library with normalized distance, coverage-as-annotation, and a mandatory delta — `cousin_engine.py` is left unmodified, the two graders encode opposite missing-dimension semantics for their respective worlds; `orchestrator.py` is LOOP, the only module that sequences a hunt iteration; `investigation.py` is the LOOP's model-calling investigation arm, adapting `blue_orchestrate.py`'s existing section runners; `contracts.py` holds the versioned boundary DTOs every command/event carries. CLI shell: the `hunt` subcommand registered in `portal/modules/security/core/__main__.py`, delegating to `hunt_main` in `portal/modules/security/core/commands/hunt_modes.py`, which owns no state and only calls the application contracts above.

## Gotchas

Boundary rules are enforced by import-scan tests, not just review: only `orchestrator.py` sequences an iteration; only `store.py` touches SQL; only `organ.py` touches the hunt-memory projection; `cousin_engine.py`/`signatures.py` are pure compute, unit-testable with `tmp_path`, no network; model calls happen only inside `investigation.py` (and later `adversary.py`/`handoff.py`/`playbooks.py`), always through the existing `agentic_blue_eval._call_model` pattern with model ids resolved as config aliases via the backends registry — never a hardcoded model tag. The package never imports MCP modules and no MCP module imports it. Production code never imports `recall_attribution` (label-blind, Rule BM). Every shadow/dual-run interface defaults `off`; legacy purple results stay byte-stable with the flag off.
