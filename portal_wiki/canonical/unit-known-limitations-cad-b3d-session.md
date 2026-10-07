---
id: unit-known-limitations-cad-b3d-session
kind: what
title: "CAD build123d sessions are per request (P5-CAD-B3D-SESSION-001)"
sources:
- type: code
  path: portal/modules/cad/tools/b123d_bridge.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- known-limitations
- cad
created_at: 1791300000
updated_at: 1791300000
---

- **ID**: P5-CAD-B3D-SESSION-001
- **Status**: ACTIVE (by design)
- **Description**: The `cad_*` tools run against an in-container `build123d-mcp` engine, and the CAD session handle is the pipeline request id: one isolated CAD session per request. Live session state (shapes registered with `show()`, variables) does not persist across chat turns or requests; the engine caps concurrent sessions (`CAD_B3D_MAX_SESSIONS`, default 4, LRU eviction by the bridge) and expires idle ones (`CAD_B3D_IDLE_TIMEOUT_S`, default 900 s).
- **Impact**: A follow-up turn ("make the holes 5 mm") cannot `cad_execute` against the previous turn's live shape.
- **Mitigation**: Continuity is carried by the saved artifacts: every `cad_finalize` publishes the build123d script (`script_url`) and the STEP; the model re-sends the (edited) script to `cad_build`. `generate_part` is stateless by construction.

## Why

Binding sessions to requests keeps the stateless-pipeline rule (CLAUDE.md rule 4) and lets the bridge bound memory (`CAD_B3D_MEMORY_LIMIT_MB`) without a session registry the pipeline would have to own.
