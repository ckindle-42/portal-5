---
id: unit-known-limitations-engine-update-data01-approval
kind: what
title: Engine Updates Need a One-Click data01 Access Approval
sources:
- type: code
  path: scripts/engine_autoupdate.py
- type: code
  path: scripts/engine_contract_check.py
claims: []
confidence: medium
tags:
- known-limitations
- ollama
- omlx
- macos
created_at: 1790333591
updated_at: 1790333591
---

- **ID**: P5-ENGINE-TCC-001
- **Status**: MITIGATED 2026-09-25 — cannot be pre-approved without MDM; the updater detects it, asks, waits and rolls back.
- **Description**: A new Ollama or oMLX binary must be allowed by macOS to read the external `data01` volume that holds the models; until someone clicks Allow on the popup the engine answers with no models. Pre-approval needs an MDM-installed privacy profile, which this host does not have.
- **Mitigation**: Ollama now always runs from the fixed real path `~/ollama-live/` (macOS keys the grant to path + Developer ID, identical across Ollama releases), so one approval should cover future upgrades — in three consecutive version switches on that path on 2026-09-25 the models stayed visible, but whether each release keeps the grant is only proven one upgrade at a time. oMLX runs under Homebrew's Python, whose path changes when brew upgrades it, so it can still prompt. `scripts/engine_autoupdate.py` compares the engine's model count before and after every switch; a drop sends a high-priority Pushover asking for the click and waits 30 minutes, then rolls back without rejecting the release and retries the next day. `engine_contract_check.py` alerts the same way when a probe model vanishes after a manual upgrade.

## Why

An unattended update that silently leaves the engine blind to its models would take every seat down while reporting success; the popup is the one step automation cannot perform, so the design makes it loud, bounded and reversible.
