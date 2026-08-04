---
id: unit-known-limitations-host-native-mcp-lifecycle-launcher-child-exit
kind: what
title: Host-Native MCPs Exited With the Launcher Process (Resolved)
sources:
- type: code
  path: scripts/native-mcp-service.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
- type: code
  path: tests/unit/test_native_mcp_service.py
- type: code
  path: scripts/validate_system.py
last_generated_commit: 6afb262648d307376dfb4f839eeed69c02112d04
claims: []
confidence: high
tags:
- known-limitations
- launchd
- mcp
- resolved
- verified-v1
created_at: 1785459600
updated_at: 1785459600
---

- **ID**: P5-NATIVE-MCP-LIFECYCLE-001
- **Status**: RESOLVED 2026-07-30.
- **Former issue**: The five declared host-native MCP services (`mlx_transcribe`,
  `pipeline`, `mitre`, `detections`, and `wiki`) were started as raw `nohup`
  children of `launch.sh`. They could exit together when the launcher process or
  its execution session ended, while their PID files remained stale. System
  validation check **BC** then failed because ports 8924, 8928, 8929, 8931, and
  8932 were declared in `config/portal.yaml` but unreachable.
- **Resolution**: On macOS, `launch.sh up` now registers those services as user
  launchd agents with `KeepAlive=true`. A shared wrapper loads the project
  environment without copying secrets into plist files and dispatches each
  service through the project's own virtual-environment interpreter. Linux keeps
  the existing PID-file-backed background-process behavior.
- **Lifecycle symmetry**: `launch.sh down` boots the five agents out of the user
  launchd domain, and `start-transcribe`/`stop-transcribe` use the same durable
  path instead of maintaining a second launch mechanism.
- **Regression proof**: All five health endpoints remained reachable after the
  launching shell returned. Terminating the launchd-managed Pipeline MCP caused
  launchd to assign a new PID and restore a healthy endpoint automatically.

## Why

Host-native MCP services must outlive the shell that started them, or the stack degrades the moment `launch.sh` returns from a non-interactive session. Running them as launchd agents with `KeepAlive=true` gives durable supervision and automatic restart, while the shared wrapper keeps secrets out of the plist files themselves. Linux retains the PID-file path because launchd is not available there; the two mechanisms share the same service names and health endpoints.
