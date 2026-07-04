---
id: unit-claude-1-config-backends-yaml-is-sacred
kind: why
title: "CLAUDE.md \u2014 1 \u2014 config/backends.yaml Is Sacred"
sources:
- type: design
  path: CLAUDE.md
  section: "1 \u2014 config/backends.yaml Is Sacred"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.806186
updated_at: 1783195000.806186
---


This is the ONLY file an operator edits to scale from 1 node to 12. Never hardcode backend URLs in Python. All backend discovery flows through `BackendRegistry`. Adding a Mac Studio cluster node means adding 6 lines of YAML, nothing else.
