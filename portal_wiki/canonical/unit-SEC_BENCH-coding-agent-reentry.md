---
id: unit-SEC_BENCH-coding-agent-reentry
kind: what
title: Security bench coding-agent re-entry notes
sources:
- type: code
  path: portal/modules/security/core/__init__.py
- type: code
  path: portal/modules/security/core/__main__.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: launch.sh
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- bench
- reentry
- security
- verified-v1
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
├── blue.py, chain.py, cli.py, matrix.py, scoring.py, ... (plus dozens more)
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

## Why

Re-entering this package after a refactor is cheap only if the module map is current; the map above is the first thing a contributor checks before adding a prompt, a scenario, or a lab hook. The rebuild triggers matter because the lab-exec lane runs inside Docker images that do not pick up Python edits automatically — only `_data.py` and `__init__.py` are hot-reloadable, so knowing which layer a change lands in determines whether a rebuild is required.
