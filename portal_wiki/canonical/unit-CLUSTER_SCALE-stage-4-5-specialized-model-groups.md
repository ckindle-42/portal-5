---
id: unit-CLUSTER_SCALE-stage-4-5-specialized-model-groups
kind: why
title: "CLUSTER_SCALE \u2014 Stage 4-5: Specialized Model Groups"
sources:
- type: design
  path: docs/CLUSTER_SCALE.md
  section: 'Stage 4-5: Specialized Model Groups'
last_generated_commit: ''
confidence: high
tags:
- docs
- CLUSTER_SCALE
created_at: 1783195000.828939
updated_at: 1783195000.828939
---


Assign different machines to different workspace groups for optimal routing:

```yaml
- id: vllm-coding
  url: "http://192.168.1.104:8000"
  group: coding      # auto-coding workspace routes here first
  models: [Qwen/Qwen2.5-Coder-32B-Instruct]

- id: vllm-creative
  url: "http://192.168.1.105:8000"
  group: creative    # auto-creative routes here first
  models: [mistral-7b-instruct-abliterated]
```

Open WebUI, the MCP tools, and the Telegram/Slack channels all continue working
unchanged. The only edit is a YAML file.
