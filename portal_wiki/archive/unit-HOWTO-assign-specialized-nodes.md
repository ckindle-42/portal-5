---
id: unit-HOWTO-assign-specialized-nodes
historical: true
kind: why
title: "HOWTO \u2014 Assign specialized nodes"
sources:
- type: design
  path: docs/HOWTO.md
  section: Assign specialized nodes
confidence: high
tags:
- docs
- HOWTO

---


```yaml
- id: vllm-coding
  url: "http://192.168.1.104:8000"
  group: coding      # auto-coding routes here first
  models: [Qwen/Qwen2.5-Coder-32B-Instruct]
```

---
