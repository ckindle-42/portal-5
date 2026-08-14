---
id: unit-SEC_BENCH-architecture-invariant
kind: why
title: 'Architecture invariant: bench never modifies Open WebUI or pipeline'
sources:
- type: code
  path: portal/modules/security/core/__init__.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: tests/benchmarks/bench_security.py
claims: []
confidence: high
tags:
- architecture
- bench
- security
- verified-v1
created_at: 1784941806.379471
updated_at: 1784941806.379471
---

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference (`call_theory_direct` in `__init__.py`)
- MCP sandbox at :8914 for command execution (`_lab_mcp_call` dispatch in `lab.py`)
- Proxmox MCP at :8927 for VM lifecycle (`_proxmox_mcp_call` in `lab.py`)

`tests/benchmarks/bench_security.py` is a backward-compat re-export shim over `portal.modules.security.core` — it re-exports names for import compatibility but has no `__main__` entry point. Run the bench via `python3 -m portal.modules.security.core ...`, not `python3 -m tests.benchmarks.bench_security`.

## Why

This invariant keeps the bench a pure consumer: it reads model outputs and issues real commands, but never mutates the Open WebUI or pipeline code it benchmarks. That separation means the bench can be re-run or pinned without touching the serving path, and its results stay attributable to the models alone rather than to harness edits. The shim exists purely so legacy import sites keep working after the module relocation.
