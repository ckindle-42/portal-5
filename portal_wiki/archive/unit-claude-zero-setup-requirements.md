---
id: unit-claude-zero-setup-requirements
historical: true
kind: why
title: "CLAUDE.md \u2014 Zero-Setup Requirements"
sources:
- type: design
  path: CLAUDE.md
  section: Zero-Setup Requirements
confidence: high
tags:
- claude
- architecture
- law

---


Every feature must work from `./launch.sh up` without manual steps. Dependencies must be installable via pip/apt-get in the Dockerfile OR a Docker service. If a dependency may fail, degrade gracefully — never crash.

---
