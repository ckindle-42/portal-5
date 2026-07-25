---
id: unit-readme-benchmark-workspaces-user-selected-only
kind: what
title: "README \u2014 Benchmark Workspaces (user-selected only)"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Benchmark Workspaces (user-selected only)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6800451
updated_at: 1784946220.6800451
---

These pin a specific model for direct performance comparison. Not intended for daily use.
Run `python3 -c "from portal.platform.inference.router.workspaces import WORKSPACES; [print(k) for k in sorted(WORKSPACES) if k.startswith('bench-')]"` for the current full list (currently 60 workspaces).

| Workspace | Pinned model |
|---|---|
| `bench-agentworld` | Qwen-AgentWorld-35B-A3B UD-Q4_K_XL |
| `bench-devstral` | Devstral-Small-2507 24B (GGUF) |
| `bench-devstral-small-2` | Devstral-Small-2 24B Dec 2025 (GGUF) |
| `bench-fastcontext` | FastContext-1.0-4B-SFT (repository explorer subagent) |
| `bench-gemma4-12b` | Gemma 4 12B Q4_K_M (ctx8k) |
| `bench-gemma4-26b-qat` | Gemma 4 26B-A4B QAT |
| `bench-gemma4-31b-crack` | Gemma-4-31B-JANG_4M-CRACK Q4_K_M |
| `bench-gemma4-e2b` | Gemma 4 E2B MoE |
| `bench-gemma4-e4b` | Gemma 4 E4B MoE Q4_K_M |
| `bench-gemma4-e4b-qat` | Gemma 4 E4B QAT |
| `bench-glm` | GLM-4.7-Flash Q4_K_M |
| `bench-glm-reap` | GLM-4.7-Flash REAP 23B-A3B UD-Q4_K_XL |
| `bench-glm-z1-rumination` | GLM-Z1-Rumination-32B Q4_K_M |
| `bench-gptoss` | GPT-OSS 20B (Ollama) |
| `bench-granite41-8b` | Granite 4.1 8B (Ollama) |
| `bench-granite41-30b` | Granite 4.1 30B (Ollama) |
| `bench-huihui-qwen36-27b` | Huihui Qwen3.6-27B abliterated |
| `bench-huihui-qwen36-35b-a3b` | Huihui Qwen3.6-35B-A3B abliterated Q4_K_M |
| `bench-laguna` | Laguna-XS.2 33B-A3B Q4_K_M (Poolside AI) |
| `bench-lfm25-8b` | LFM2.5-8B-A1B (Liquid AI hybrid architecture) |
| `bench-lfm25-8b-uncensored` | LFM2.5-8B uncensored |
| `bench-nex-n2-mini` | Nex-N2-mini UD-Q4_K_M (Nex AGI) |
| `bench-omnicoder2` | OmniCoder-2 9B Q4_K_M |
| `bench-qwable-35b` | Qwable-3.6-35B Q4_K_M |
| `bench-qwen35-abliterated` | Qwen3.5-9B abliterated (Ollama) |
| `bench-qwen36-27b` | Qwen3.6-27B Q4_K_M |
| `bench-qwen36-35b-a3b` | Qwen3.6-35B-A3B MoE Q4_K_M |
| `bench-qwen36-35b-a3b-ud` | Qwen3.6-35B-A3B UD-Q4_K_XL (Unsloth Dynamic) |
| `bench-qwen3-coder-30b` | Qwen3-Coder 30B MoE A3B Q4_K_M |
| `bench-qwen3-coder-next` | Qwen3-Coder-Next 80B MoE Q4_K_M |
| `bench-qwen3-coder-next-abliterated` | Huihui Qwen3-Coder-Next abliterated Q4_K_M |
| `bench-sylink` | sylink:8b (SOC triage, DFIR, ATT&CK) |
| `bench-vulnllm-r7b` | VulnLLM-R-7B Q4_K_M |
| *(+ 15 more)* | Security exec chain, LFM micro, MTP, security bench lanes |

---
