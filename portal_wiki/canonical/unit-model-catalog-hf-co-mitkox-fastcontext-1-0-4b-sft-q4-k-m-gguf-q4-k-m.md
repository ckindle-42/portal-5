---
id: unit-model-catalog-hf-co-mitkox-fastcontext-1-0-4b-sft-q4-k-m-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6134982
updated_at: 1784946220.6134982
---

FastContext-1.0-4B-SFT Q4_K_M (~2.5GB, Microsoft arxiv:2606.14066, mitkox GGUF quant). Repository-exploration SUBAGENT: issues parallel READ/GLOB/GREP tool calls to locate relevant code, returns compact file+line citations. Reduces main-agent exploration token burn by ~50-60% on SWE-bench. Used by pipeline_mcp.explore_repository() — called by auto-coding-agentic before edits. NOT for direct workspace routing. supports_tools=true (READ/GLOB/GREP are its three native tools per paper). Pull: ollama pull hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M
