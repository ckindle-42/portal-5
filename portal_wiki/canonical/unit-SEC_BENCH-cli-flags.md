---
id: unit-SEC_BENCH-cli-flags
kind: what
title: CLI flags for security bench
sources:
- type: code
  path: portal/modules/security/core/cli.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- bench
- cli
- security
- verified-v1
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

## Why

These flags split the bench into three orthogonal axes: where work runs (pipeline vs direct lab dispatch), which model assignment the chain uses (round-robin vs step DAG vs explicit roster), and which extras are enabled (blue active response, lab snapshots, service probing). Keeping each behind a flag means the same CLI serves fleet-wide theory sweeps and live lab-exec validation without separate entry points — and a flag's default encodes the safe choice: snapshots and active response are opt-in, never on by default.
