---
id: unit-SECURITY_BENCH_EXEC-architecture-invariant
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Architecture invariant"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Architecture invariant
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference
- MCP sandbox at :8914 for command execution
- Proxmox MCP at :8927 for VM lifecycle
