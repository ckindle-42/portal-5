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

`TASK_BULLY_UNKNOWN_COUSIN_V1` layers a unit-of-analysis correction on top of the observed path: `artifact_graph.py` builds the artifact graph and structural gradeable units (`L1_ARTIFACT`/`L2_ENTITY`/`L3_CHAIN`/`L4_WINDOW`) a window's records actually produce; `unit_relation.py` grades a unit against a known type on separate shape and vocabulary channels; `baseline.py` is the per-environment normal-frequency model units are scored against (never matched); `unit_outcome.py` resolves the outcome table (`KNOWN_INSTANCE`/`UNKNOWN_SAME`/`COUSIN`/`RECOGNIZED_NORMAL`/`NORMAL`/`NOVEL`/`INSUFFICIENT_VIEW`) into `ConcernBrief`s and writes investigated outcomes back as typed anchors; `unit_measurement.py` is the grading-plane legend binding, held-out split, precision/recall, and leave-one-family-out measurement stack; `unit_ladder.py` is the combination-level falsification instrument. `anchors.py` gained a fifth kind, `benign_pattern` (malice-carrying, N.1). None of this touches `cousin_engine.py`/`relation.py`.

`TASK_BULLY_UNIVERSAL_INTAKE_AND_INJECT_V1` corrects the unit model's intake, which `artifact_graph.py` had left CloudTrail-shaped: `field_roles.py` infers each field's ENTITY/TIMESTAMP/ACTION/PAYLOAD/CONSTANT role from how its *values* behave (cardinality, structure, time-parseability), never from a field-name list, and decides source-level `extraction_valid`; `artifact_graph.build_graph` now consumes a `FieldRoleMap` and refuses to emit any unit from a source whose extraction failed (Q1) instead of silently collapsing to an all-`other` shape. `blend.py` is the deterministic, offline multi-schema fixture (CloudTrail/Sysmon/osquery/firewall-syslog, zero shared field names) proving plurality in CI (Q2); `inject_plane.py` plus `scripts/bully_inject_capture.py` are the permanent live sibling -- generate labelled activity via the existing `lab.dispatch_lab_tool`, capture it back through the existing `live_connect.SplunkQueryInPlaceConnector`, and seal ground truth through the existing `specimen_ledger.SpecimenLedger` (`source_lane="live_lab"`, Q3) -- both fail closed and state which plane produced a run's numbers, never a silent synthetic substitute. `baseline.py`'s fitted statistics are now partitioned by `GradeableUnit.level`, closing a fit/score level mismatch that produced a content-independent remarkability floor. `unit_ladder.run_ladder` validates monotonicity on `shape_distance` (the variable `resolve_unit_outcome` actually decides on) rather than a blended `combined_distance`. `unit_outcome._unobservable_channels` and `unit_measurement.run_leave_one_family_out` (split `cousin_recall`/`novelty_recall`, absolute-vs-conditional recall) close the remaining measurement-honesty gaps found in the same review.

## Gotchas

Boundary rules are enforced by import-scan tests, not just review: only `orchestrator.py` sequences an iteration; only `store.py` touches SQL; only `organ.py` touches the hunt-memory projection; `cousin_engine.py`/`signatures.py` are pure compute, unit-testable with `tmp_path`, no network; model calls happen only inside `investigation.py` (and later `adversary.py`/`handoff.py`/`playbooks.py`), always through the existing `agentic_blue_eval._call_model` pattern with model ids resolved as config aliases via the backends registry — never a hardcoded model tag. The package never imports MCP modules and no MCP module imports it. Production code never imports `recall_attribution` (label-blind, Rule BM). Every shadow/dual-run interface defaults `off`; legacy purple results stay byte-stable with the flag off.
