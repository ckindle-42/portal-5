---
id: unit-cluster-scale-stage-3-vllm-for-70b-models
kind: what
title: "CLUSTER_SCALE \u2014 Stage 3: vLLM for 70B Models"
sources:
- type: doc
  path: docs/CLUSTER_SCALE.md
  commit: 05e42ec2
  section: 'Stage 3: vLLM for 70B Models'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5125499
updated_at: 1784946220.5125499
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
