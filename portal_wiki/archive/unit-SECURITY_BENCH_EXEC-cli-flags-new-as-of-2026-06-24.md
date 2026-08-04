---
id: unit-SECURITY_BENCH_EXEC-cli-flags-new-as-of-2026-06-24
kind: why
title: "SECURITY_BENCH_EXEC \u2014 CLI Flags (New as of 2026-06-24)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: CLI Flags (New as of 2026-06-24)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8988779
updated_at: 1783195000.8988779
---


| Flag | Purpose |
|------|---------|
| `--lab-exec` | Real MCP sandbox dispatch (execute_bash → portal5-attack container) |
| `--lab-snapshot` | Snapshot VMs via Proxmox before chain, restore after — clean state per prompt |
| `--probe-lab` | Auto-discover which lab services are reachable, print report |
| `--blue-active` | Blue defender can call `block_ip`/`disable_account`/`revoke_tgt` in the lab |
| `--chain-dag` | Use step dependency DAG for model assignment (topological sort) |
| `--chain-rounds N` | Number of full passes through all chain models (default: 1, use 2+ for follow-up) |
| `--exec-chain-models` | 2-4 Ollama model IDs for multi-model execution chain |
| `--blue-defender-model` | Ollama model ID for blue team SOC analysis |
| `--skip-workspace-bench` | Skip theory/exec pipeline passes; run chain tests only |

---
