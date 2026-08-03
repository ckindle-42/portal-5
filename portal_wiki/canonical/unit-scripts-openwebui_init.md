---
id: unit-scripts-openwebui_init
kind: mixed
title: "Script \u2014 openwebui_init"
sources:
- type: code
  path: scripts/openwebui_init.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799543.3560672
updated_at: 1785799543.3560672
---

Runs inside the Open WebUI init container after OWUI is healthy: admin account creation (idempotent), persona seeding, and workspace preset installation.

## Why

A fresh Open WebUI needs its admin, personas, and workspace presets provisioned before it is usable, and the init container is where that happens once — with idempotence so a re-run does not duplicate the admin or the presets.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
