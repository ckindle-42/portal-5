---
id: unit-known-limitations-code-sandbox-requires-privileged-container
kind: what
title: "KNOWN_LIMITATIONS \u2014 Code Sandbox Requires Privileged Container"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Code Sandbox Requires Privileged Container
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.661224
updated_at: 1784946220.661224
---

- **ID**: P5-ROAD-SEC-001
- **Description**: The `dind` (Docker-in-Docker) service runs with `privileged: true`. Docker-in-Docker cannot function without host kernel capabilities.
- **Impact**: In hardened environments, a compromised sandbox container could potentially escape to host.
- **Mitigation**: Disable the code sandbox by removing `mcp-sandbox` and `dind` from `docker-compose.yml`, or apply host-level controls (AppArmor/seccomp on the Docker daemon).
