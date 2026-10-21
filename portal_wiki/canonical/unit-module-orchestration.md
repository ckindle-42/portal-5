---
id: unit-module-orchestration
kind: mixed
title: "Orchestration Module — offline verified task runner (off by default)"
sources:
- type: code
  path: portal/modules/orchestration/__init__.py
- type: code
  path: portal/modules/orchestration/service.py
- type: code
  path: portal/modules/orchestration/worker.py
- type: code
  path: portal/modules/orchestration/cli.py
- type: code
  path: portal/modules/orchestration/plugin.py
- type: code
  path: portal/modules/orchestration/ledger.py
- type: code
  path: portal/modules/orchestration/contracts.py
- type: code
  path: portal/platform/inference/cli/_apps.py
- type: code
  path: portal/platform/inference/cli/__init__.py
- type: code
  path: portal/platform/wiki/adapters/modules.py
- type: code
  path: portal/platform/inference/config.py
- type: config
  path: config/portal.yaml
claims:
- probe: modules.disabled
  contains: orchestration
confidence: high
tags:
- orchestration
- module
- verified-v1
created_at: 1792546230.261703
updated_at: 1792546273.110409
---

# Orchestration Module — offline verified task runner

## What it is

The orchestration module exposes `portal arm submit`, `resume`, and `status` for hand-written bite plans. Its own package lives under `portal/modules/orchestration/`; it uses the Pipeline chat endpoint and does not import or wrap `portal/platform/agent/run_loop`. A bite gets a fresh Pipeline request with the `auto-daily::fast` or `auto-daily::deep` seat, a per-request tool allowlist, a transcript, a finish requirement, and deterministic checks.

## Phase 1 boundary

The skeleton is offline-tested against a fake OpenAI-compatible Pipeline API. It has no planner, Open WebUI entry point, Deep review, or Telegram transport. The default block-notice sink is a stub. Live acceptance remains outside this offline phase.

## Module state

The switch is `modules.orchestration.enabled` in `config/portal.yaml` and defaults to false. The module unit documents the switch; it does not hold it. `config/orchestration_arm.yaml` supplies the default `swap` residency mode and the underlying model IDs checked by the Pipeline load guard.

## Why

Security owns `portal/platform/agent/run_loop` as its goal loop. Keeping the arm in its own module package leaves that boundary intact while the Pipeline's tool loop handles each bite.
