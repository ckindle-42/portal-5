---
id: unit-QWEN_TEMPLATE_PROBE-server-flag-support
historical: true
kind: why
title: "QWEN_TEMPLATE_PROBE \u2014 Server flag support"
sources:
- type: design
  path: docs/QWEN_TEMPLATE_PROBE.md
  section: Server flag support
confidence: high
tags:
- docs
- QWEN_TEMPLATE_PROBE

---


| Flag | mlx_lm.server | mlx_vlm.server |
|---|---|---|
| `--chat-template` | PRESENT | ABSENT |
| `--chat-template-file` | ABSENT | ABSENT |
| `--jinja` | ABSENT | ABSENT |
| `--template` | ABSENT | ABSENT |
