---
id: unit-HOWTO-3-workspaces
kind: why
title: "HOWTO \u2014 3. Workspaces"
sources:
- type: design
  path: docs/HOWTO.md
  section: 3. Workspaces
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.839686
updated_at: 1783195000.839686
---


**What:** Each workspace routes to a specialized model and activates relevant tools.

**How:** Select a workspace from the model dropdown in the top bar.

| Workspace | Select this when... | Routes to |
|-----------|---------------------|-----------|
| Portal Auto Router | You're unsure | LLM router classifies intent → best-fit workspace (Ollama) |
| Portal Daily Driver | Everyday chat, writing, summarization, planning (snappy) | Gemma-4-26B-A4B-IT (Ollama) |
| Portal Code Expert | Writing or reviewing code | Qwen3-Coder-30B MoE (Ollama) |
| Portal Security Analyst | Security questions | Qwen3.6-27B (Ollama) · BaronLLM (Ollama) |
| Portal Red Team | Offensive security | Qwen3.6-27B (Ollama) · BaronLLM (Ollama) |
| Portal Blue Team | Incident response | sylink:8b (Ollama) — SOC triage, DFIR, ATT&CK |
| Portal Creative Writer | Stories, scripts | Gemma-4-heretic (Ollama) · Dolphin (Ollama) |
| Portal Deep Reasoner | Complex analysis | Qwen3.6-27B (Ollama) · DeepSeek-R1 (Ollama) |
| Portal Document Builder | Word/Excel/PPT files | Granite-4.1-8B (Ollama) + Documents MCP |
| Portal Video Creator | Text-to-video | Granite-4.1-8B (Ollama) + Video MCP |
| Portal Music Producer | Generate music | Qwen3.5-abliterated (Ollama) + Music MCP |
| Portal Research Assistant | Web research | Gemma-4-26B-A4B-IT (Ollama) · Tongyi-DeepResearch (Ollama) |
| Portal Vision | Image analysis | Gemma-4-26B-A4B-IT (Ollama) · Qwen3-VL (Ollama) |
| Portal Data Analyst | Statistics, analysis | Granite-4.1-30B (Ollama) |
| Portal Compliance Analyst | NERC CIP gap analysis, policy-to-standard mapping | Granite-4.1-30B (Ollama) · DeepSeek-R1 (Ollama) |
| Portal Mistral Reasoner | Structured reasoning, strategic planning | Magistral-Small (Ollama) |
| Portal SPL Engineer | Writing or debugging Splunk SPL queries | Qwen3-Coder-Next-abliterated 80B (Ollama) |
| Portal Agentic Coder (Heavy) | Long-horizon multi-file agentic coding tasks | Qwen3-Coder-Next 80B (Ollama) |

**Example — coding:**
1. Selec
