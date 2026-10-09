---
id: unit-capability-security-review
kind: mixed
title: "Security Review MCP — durable, evidence-grounded analyst review"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: config/portal.yaml
  section: workspaces
- type: code
  path: config/personas/securityreviewer.yaml
- type: code
  path: config/security/tools_manifest_review_mcp.json
- type: code
  path: portal/modules/security/tools/review_mcp.py
- type: code
  path: portal/modules/security/core/review/service.py
- type: code
  path: portal/modules/security/core/review_cli.py
- type: code
  path: scripts/native-mcp-service.sh
- type: code
  path: scripts/validation/review_program.py
- type: code
  path: tests/security/review/test_runtime.py
claims:
- probe: mcp.fleet.ports
  contains: 8943
- probe: workspaces.exposed
  contains: security-reviewer
confidence: high
tags:
- capability
- mcp
- security
- review
---

# Security Review MCP — durable, evidence-grounded analyst review

## What

The host-native Review MCP runs on port 8943 and exposes eight lifecycle tools:
start, status, result, cancel, verdict, queue, explain, and doctor. It reads
already-indexed Splunk telemetry, stores durable run and verdict records under
`PORTAL5_REVIEW_DIR` (default `~/AI_Output/review`), and marks unfinished runs
`INTERRUPTED` after a process restart.

The `security-reviewer` workspace and `securityreviewer` persona bind those
tools to a read-only analyst workflow. T3's installed reviewer default is
`no_reader`: the review engine does not make a model verdict. The chat model
helps the analyst use the tools; the analyst owns every verdict.

## Evidence contract

`review_explain` returns a concern's claims and the exact event text the
reviewer saw for every cited event. A missing event quote is an error, not a
blank citation. `review_verdict` records an analyst decision and updates the
open queue. Neither a machine opinion nor a concern candidate is an analyst
decision.

## Embedder changes

`review_doctor` reports each stored calibration's embedder identity, Splunk
reachability and index counts, reasoning models, database integrity, and the
last run's status. When the embedder identity changes, `review_doctor(fix=true)`
rebuilds anchor vectors from stored card text and refits similarity nulls from
the private recorded benign slice. A run refuses stale calibrations and gives
the analyst the doctor repair command.

The MCP is host-native because it needs Splunk, the loopback embedding service,
and the private local review directory. Its only telemetry reads are indexed
searches; it has no attack, chain, target-execution, or emulation operation.

## CLI

The same service is available through
`python -m portal.modules.security.core review run|status|result|verdict|queue|explain|doctor`.
The `review_program` system check runs both review test suites and validates
the derived review state.
