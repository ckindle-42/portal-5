---
id: unit-readme-functional-workspaces
kind: what
title: "README \u2014 Functional Workspaces"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Functional Workspaces
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.679698
updated_at: 1784946220.679698
---

| Workspace | Purpose | Auto-activates |
|---|---|---|
| `auto` | General — routes to best model for each task | — |
| `auto-daily` | Fast everyday assistant — chat, writing, summarization, planning | web_search, memory, documents |
| `auto-coding` | One-shot code generation and review (Qwen3-Coder-30B MoE). 7 former sibling workspaces are now `?variant=` query params or a persona's `variant:` field on this base workspace — `laguna` (Laguna-XS.2, self-improvement agentic), `uncensored`, `uncensored-agentic`, `heavy` (Qwen3-Coder-Next 80B, long-horizon), `lite` (AgentWorld 35B), `ornith` (Ornith-1.0 35B), `northmini` (North-Mini-Code) | Code sandbox |
| `auto-reasoning` | Extended reasoning, complex analysis | — |
| `auto-council` | Opt-in review: three isolated evidence/challenger/operator seats, full-roster quorum, preserved dissent, and bounded synthesis | — |
| `auto-research` | Web research and synthesis | web_search, web_fetch |
| `auto-vision` | Image understanding, visual Q&A (Qwen3-VL 32B) | — |
| `auto-creative` | Creative writing with voice output | TTS |
| `auto-documents` | Create Word, Excel, PowerPoint | Documents + Code |
| `auto-data` | Data analysis, statistics, charting (Granite 4.1 30B) | Code + Documents |
| `auto-math` | Mathematical problem solving, proofs, calculus | Code sandbox |
| `auto-audio` | Audio processing and transcription | Transcribe |
| `auto-music` | Generate music via MusicGen | Music |
| `auto-video` | Generate video via ComfyUI | Video |
| `auto-image` | Generate images via ComfyUI (Flux/SDXL), generation-first | Image |
| `auto-cad` | 3D CAD model generation — OpenSCAD, CadQuery | CAD render |
| `auto-spl` | Splunk SPL queries, YARA rules, detection search | — |
| `auto-compliance` | NERC CIP gap analysis, policy review, audit prep (Granite 4.1 30B) | — |
| `auto-bigfix` | IBM BigFix relevance scripting | — |
| `auto-security` | Security analysis, CVE triage, hardening (VulnLLM-R-7B). 8 former sibling workspaces are now `?variant=` query params or a persona's `variant:` field on this base workspace — `uncensored`, `pentest` (Qwen3.6-35B-A3B-Uncensored-HauhauCS, live execution — P5-AUTOSEC-RESELECT 2026-07-16), `blueteam` (sylink:8b, threat hunting), `redteam`/`redteam-deep` (SuperGemma4-26B), `purpleteam`/`purpleteam-deep`/`purpleteam-exec` (2/4-hop red→blue chains, exec = live attack + detection + IR playbook) | web_search, kb_search (exec/pentest variants add execute_bash, execute_python) |
| `auto-general-uncensored` | General uncensored assistant | — |
| `auto-extract-uncensored` | Uncensored information extraction | — |
| `tools-specialist` | Tool-use specialist — structured output, function calling (Granite 4.1 8B) | — |
