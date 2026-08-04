---
id: unit-CLUSTER_SCALE-stage-1-stage-2-add-a-second-mac-studio
kind: why
title: "CLUSTER_SCALE \u2014 Stage 1 \u2192 Stage 2: Add a Second Mac Studio"
sources:
- type: design
  path: docs/CLUSTER_SCALE.md
  section: "Stage 1 \u2192 Stage 2: Add a Second Mac Studio"
last_generated_commit: ''
confidence: high
tags:
- docs
- CLUSTER_SCALE
created_at: 1783195000.828442
updated_at: 1783195000.828442
---


1. Install Ollama on the new Mac Studio
2. Configure it to listen on the network:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```
3. Add to config/backends.yaml:
   ```yaml
   - id: ollama-node-2
     type: ollama
     url: "http://192.168.1.102:11434"
     group: general
     models: [dolphin-llama3:8b]
   ```
4. Restart the pipeline container:
   ```bash
   docker compose restart portal-pipeline
   ```

Portal automatically discovers the new backend and load-balances across both.
