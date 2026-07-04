---
id: unit-HOWTO-add-a-second-mac-studio
kind: why
title: "HOWTO \u2014 Add a second Mac Studio"
sources:
- type: design
  path: docs/HOWTO.md
  section: Add a second Mac Studio
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8599622
updated_at: 1783195000.8599622
---


1. Install Ollama on the new machine:
   ```bash
   OLLAMA_HOST=0.0.0.0 ollama serve
   ```

2. Edit `config/backends.yaml`:
   ```yaml
   - id: ollama-node-2
     type: ollama
     url: "http://192.168.1.102:11434"
     group: general
     models: [dolphin-llama3:8b]
   ```

3. Restart the pipeline:
   ```bash
   docker compose -f deploy/portal-5/docker-compose.yml restart portal-pipeline
   ```
