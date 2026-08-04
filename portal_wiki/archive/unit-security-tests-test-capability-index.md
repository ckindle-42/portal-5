---
id: unit-security-tests-test-capability-index
kind: what
title: Capability index unit tests
sources:
- type: code
  path: portal/modules/security/tests/test_capability_index.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_capability_index.py` exercises the capability catalog layer end to end: inventory loading, index construction, querying, rendering, and the CLI entry point. The central invariant is that every capability's `tools` and `oracle` fields must resolve to something real, so the suite asserts there are no orphan references into the tool catalog or `ORACLES`. Query tests cover phase, domain, goal, and limit filtering plus the `live_dispatchable_only` flag, which retires capability sources that cannot be dispatched against a live lab while keeping semantic probes that need no declared tool. Rendering tests confirm the text output contains the expected names and degrades to a placeholder for an empty list. A subprocess-based CLI suite drives `python -m portal.modules.security.core capability` and checks that JSON output parses.

## Why

An orphan reference — a capability naming a tool that is not in the catalog or an oracle not in `ORACLES` — is a build-time bug that would otherwise surface only as a confusing runtime failure mid-engagement. Enforcing the no-orphan invariant both inside `build_index()` and independently here means the catalog can grow by editing declarative files with confidence, and the live-dispatchable distinction prevents the model from being handed capabilities that cannot actually run.
