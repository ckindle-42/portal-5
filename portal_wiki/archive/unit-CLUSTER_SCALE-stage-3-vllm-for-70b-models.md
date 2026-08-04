---
id: unit-CLUSTER_SCALE-stage-3-vllm-for-70b-models
kind: why
title: "CLUSTER_SCALE \u2014 Stage 3: vLLM for 70B Models"
sources:
- type: design
  path: docs/CLUSTER_SCALE.md
  section: 'Stage 3: vLLM for 70B Models'
last_generated_commit: ''
confidence: high
tags:
- docs
- CLUSTER_SCALE
created_at: 1783195000.8286772
updated_at: 1783195000.8286772
---


When ready to run 70B+ models (Llama 3.1 70B, etc.) via vLLM:

1. Install vLLM on the target machine
2. Start vLLM:
   ```bash
   vllm serve meta-llama/Llama-3.1-70B-Instruct --port 8000
   ```
3. Add to config/backends.yaml:
   ```yaml
   - id: vllm-70b
     type: openai_compatible
     url: "http://192.168.1.103:8000"
     group: general
     models: [meta-llama/Llama-3.1-70B-Instruct]
   ```
