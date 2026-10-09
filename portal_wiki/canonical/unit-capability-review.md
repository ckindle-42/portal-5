---
id: unit-capability-review
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

## Value

An analyst can start a review, check its progress, inspect candidate evidence,
record a verdict, and see unresolved work through the same Portal workspace,
CLI, and MCP lifecycle. Durable state survives process restarts, while an
unfinished run is explicitly marked `INTERRUPTED` instead of appearing live.

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

`PORTAL5_REVIEW_EMBEDDING_DIM` selects the EG2 Matryoshka dimension used by the
review embedder (default 768; supported dimensions are 768, 512, 256, and 128).
Changing it changes the embedder identity; `review_doctor(fix=true)` reprojects
the anchor index and refits the benign null before new runs are accepted.

## Why

The earlier hunt loop could leave work marked `running` without a process that
owned its lifecycle. A durable run store gives each request a terminal state,
progress record, result, and restart boundary. Separating candidate evidence
from analyst verdicts keeps machine output from silently becoming ground truth.

The MCP is host-native because it needs Splunk, the loopback embedding service,
and the private local review directory. Its only telemetry reads are indexed
searches; it has no attack, chain, target-execution, or emulation operation.

## CLI

The same service is available through
`python -m portal.modules.security.core review run|status|result|verdict|queue|explain|doctor`.
The `review_program` system check runs both review test suites and validates
the derived review state.
