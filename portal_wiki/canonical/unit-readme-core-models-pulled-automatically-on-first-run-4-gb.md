---
id: unit-readme-core-models-pulled-automatically-on-first-run-4-gb
kind: what
title: "README \u2014 Core models (pulled automatically on first run, ~4 GB)"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Core models (pulled automatically on first run, ~4 GB)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.685955
updated_at: 1784946220.685955
---

- `dolphin-llama3:8b` — general purpose default
- `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` — LLM router fallback/standby (uncensored 3B). Router primary is `gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M` (pulled with `pull-models`)
- `nomic-embed-text` — document embeddings for RAG
