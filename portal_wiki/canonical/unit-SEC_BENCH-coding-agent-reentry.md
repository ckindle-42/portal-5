---
id: unit-SEC_BENCH-coding-agent-reentry
kind: what
title: Security bench coding-agent re-entry notes
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/__init__.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- reentry
created_at: 1784945192.270462
updated_at: 1784945192.270462
---

## File locations after refactor

```
portal/modules/security/core/
├── _data.py        <- Add new prompts, EXEC_SEQUENCES, CHAIN_INHERITANCE here
├── __init__.py     <- Package facade (pipeline I/O, re-exports)
├── __main__.py     <- CLI entry (do not modify)
├── exec_chain.py   <- _run_exec_chain() now lives here
├── lab.py          <- _lab_mcp_call, _proxmox_mcp_call
├── blue.py, chain.py, cli.py, matrix.py, scoring.py, ... (~30 more modules)
```

## Architecture invariant

The bench NEVER modifies Open WebUI or the pipeline. It communicates directly with:
- Ollama at :11434 for model inference
- MCP sandbox at :8914 for command execution
- Proxmox MCP at :8927 for VM lifecycle

## Rebuild triggers

```bash
# After Dockerfile.attack change:
./launch.sh build-lab-attack
# After code_sandbox_mcp.py change:
./launch.sh restart-mcp
# After _data.py or __init__.py change:
# No rebuild needed — Python picks up changes directly
```
