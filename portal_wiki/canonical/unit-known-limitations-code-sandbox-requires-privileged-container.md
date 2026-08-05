---
id: unit-known-limitations-code-sandbox-requires-privileged-container
kind: what
title: "KNOWN_LIMITATIONS \u2014 Code Sandbox Requires Privileged Container"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/coding/tools/code_sandbox_mcp.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.661224
updated_at: 1784946220.661224
---

- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service in `deploy/portal-5/docker-compose.yml` runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities; the compose comment documents that `docker:dind-rootless` needs kernel user-namespace support unavailable in Docker Desktop's LinuxKit VM, so privileged DinD is accepted there. `mcp-sandbox` (port 8914) dispatches code execution through this DinD engine.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to the host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from the compose file, or apply host-level controls (AppArmor/seccomp on the Docker daemon). On bare-metal Linux hosts, the compose comments describe the rootless alternative.

## Why

The isolation boundary on macOS lives in Docker Desktop's LinuxKit VM, so privileged DinD does not add a second escape surface there; on bare-metal Linux the same flag does. Recording the tradeoff inline at the `privileged: true` site keeps the security decision visible to anyone editing the compose file and names the rootless configuration as the Linux escape hatch.
