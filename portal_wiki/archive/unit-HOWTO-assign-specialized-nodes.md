---
id: unit-HOWTO-assign-specialized-nodes
kind: why
title: "HOWTO \u2014 Assign specialized nodes"
sources:
- type: design
  path: docs/HOWTO.md
  section: Assign specialized nodes
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.860412
updated_at: 1783195000.860412
---


```yaml
- id: vllm-coding
  url: "http://192.168.1.104:8000"
  group: coding      # auto-coding routes here first
  models: [Qwen/Qwen2.5-Coder-32B-Instruct]
```

---
