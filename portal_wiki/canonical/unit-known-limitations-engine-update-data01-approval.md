---
id: unit-known-limitations-engine-update-data01-approval
kind: what
title: Engine Updates Need a One-Click data01 Access Approval
sources:
- type: code
  path: scripts/engine_autoupdate.py
- type: code
  path: scripts/engine_contract_check.py
- type: code
  path: scripts/omlx_venv_install.py
- type: code
  path: deploy/launchd/com.portal5.omlx.plist
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
- **Status**: MITIGATION READY 2026-10-21 — fixed-path signed interpreter support is in the repository; host cutover and its first approval check remain pending.
- **Description**: macOS must grant each executable identity access to the external `data01` volume that holds the models. Homebrew's ad-hoc signed Python changes identity when the formula upgrades Python, so a new build can trigger another Allow popup. Pre-approval needs an MDM-installed privacy profile, which this host does not have.
- **Mitigation**: Ollama runs from fixed `~/ollama-live/` with a stable Developer ID requirement. The oMLX installer uses a fixed `~/omlx-live/venv` backed by a Developer ID-signed ARM64 python.org framework interpreter, and the updater replaces only the package in a staged copy at that path. The interpreter path and signing identity therefore stay constant across oMLX wheel upgrades; the first post-cutover access and later releases still require model-count verification. `scripts/engine_autoupdate.py` compares model counts after a switch; a drop sends a high-priority Pushover request and waits 30 minutes before restoring the previous version and retrying the next day. `engine_contract_check.py` alerts the same way when a probe model vanishes after a manual upgrade.

## Why

An unattended update that silently leaves the engine blind to its models would take every seat down while reporting success; the popup is the one step automation cannot perform, so the design makes it loud, bounded and reversible.
