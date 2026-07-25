---
id: unit-SEC_BENCH-cli-flags
kind: what
title: CLI flags for security bench
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: d869257b
- type: code
  path: portal/modules/security/core/cli.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- security
- bench
- cli
created_at: 1784941806.3791192
updated_at: 1784941806.3791192
---

| Flag | Purpose |
|------|---------|
| `--lab-exec` | Real MCP sandbox dispatch (execute_bash -> portal5-attack container) |
| `--lab-snapshot` | Snapshot VMs via Proxmox before chain, restore after |
| `--probe-lab` | Auto-discover which lab services are reachable, print report |
| `--blue-active` | Blue defender can call `block_ip`/`disable_account`/`revoke_tgt` in the lab |
| `--chain-dag` | Use step dependency DAG for model assignment (topological sort) |
| `--chain-rounds N` | Number of full passes through all chain models (default: 1) |
| `--exec-chain-models` | 2-4 Ollama model IDs for multi-model execution chain |
| `--blue-defender-model` | Ollama model ID for blue team SOC analysis |
| `--skip-workspace-bench` | Skip theory/exec pipeline passes; run chain tests only |
