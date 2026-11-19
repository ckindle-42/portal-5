---
id: unit-HOWTO-add-a-vllm-node-for-70b-models
historical: true
kind: why
title: "HOWTO \u2014 Add a vLLM node for 70B models"
sources:
- type: design
  path: docs/HOWTO.md
  section: Add a vLLM node for 70B models
confidence: high
tags:
- docs
- HOWTO

---


```yaml
- id: vllm-70b
  type: openai_compatible
  url: "http://192.168.1.103:8000"
  group: general
  models: [meta-llama/Llama-3.1-70B-Instruct]
```
