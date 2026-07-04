---
id: unit-SECURITY_BENCH_EXEC-architecture-invariant
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Architecture invariant"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Architecture invariant
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.91311
updated_at: 1783195000.91311
---

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference
- MCP sandbox at :8914 for command execution
- Proxmox MCP at :8927 for VM lifecycle
