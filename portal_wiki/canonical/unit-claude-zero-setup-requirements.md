---
id: unit-claude-zero-setup-requirements
kind: why
title: "CLAUDE.md \u2014 Zero-Setup Requirements"
sources:
- type: design
  path: CLAUDE.md
  section: Zero-Setup Requirements
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.8107252
updated_at: 1783195000.8107252
---


Every feature must work from `./launch.sh up` without manual steps. Dependencies must be installable via pip/apt-get in the Dockerfile OR a Docker service. If a dependency may fail, degrade gracefully — never crash.

---
