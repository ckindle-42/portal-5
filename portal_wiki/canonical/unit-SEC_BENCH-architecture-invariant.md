---
id: unit-SEC_BENCH-architecture-invariant
kind: why
title: 'Architecture invariant: bench never modifies Open WebUI or pipeline'
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: portal/modules/security/core/__init__.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- architecture
created_at: 1784941806.379471
updated_at: 1784941806.379471
---

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference
- MCP sandbox at :8914 for command execution
- Proxmox MCP at :8927 for VM lifecycle

`tests/benchmarks/bench_security.py` is a backward-compat re-export shim over `portal.modules.security.core` -- it re-exports names for import compatibility but has no `__main__` entry point. Run the bench via `python3 -m portal.modules.security.core ...`, not `python3 -m tests.benchmarks.bench_security`.
