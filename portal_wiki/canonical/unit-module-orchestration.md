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
  path: portal/modules/orchestration/owui_entry.py
- type: code
  path: portal/modules/orchestration/queue.py
- type: code
  path: portal/modules/orchestration/planner.py
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
- type: code
  path: portal/platform/inference/router/eval_gate.py
- type: code
  path: tests/wfe/runner.py
- type: code
  path: tests/unit/orchestration_fake_pipeline.py
- type: code
  path: scripts/orchestration_bite_suite.py
- type: code
  path: scripts/gate_c_calculator.py
claims:
- probe: modules.disabled
  contains: orchestration
confidence: high
tags:
- orchestration
- module
- verified-v1
created_at: 1792546230.261703
updated_at: 1792680000
---

# Orchestration Module — offline verified task runner

## What it is

The orchestration module exposes `portal arm submit`, `resume`, and `status` for hand-written bite plans. Its own package lives under `portal/modules/orchestration/`; it uses the Pipeline chat endpoint and does not import or wrap `portal/platform/agent/run_loop`. A bite gets a fresh Pipeline request with the `auto-daily::fast` or `auto-daily::deep` seat, a per-request tool allowlist, a transcript, a finish requirement, and deterministic checks.

## Phase 1 boundary

Offline tests drive the arm through a fake OpenAI-compatible Pipeline API. Stored plan templates enqueue through `QueueLedger.enqueue`. Open WebUI reaches that queue through the pipeline MCP tool `arm_queue_task` (`portal/modules/orchestration/owui_entry.py`). The module stays disabled by default. Live model acceptance remains outside this offline phase.

## Module state

The switch is `modules.orchestration.enabled` in `config/portal.yaml` and defaults to false. The module unit documents the switch; it does not hold it. `config/orchestration_arm.yaml` supplies the default `swap` residency mode and the underlying model IDs checked by the Pipeline load guard.

## Live bites

The arm cannot run a live bite yet. The worker's `portal_bite_tools` list is an allowlist. `apply_bite_tool_scope` filters tools the pipeline already has, and the only client schema the worker attaches is `finish`. The bite tool implementations live in `tests/wfe/runner.py`. The fake pipeline scripts the engine, not the decisions: bearer auth, `tools_offered` (through the production `apply_bite_tool_scope` over a declared registry, default exactly the allowlisted names), and the SSE wire are production code, pinned by parity tests. Task-scoped client tools are being built on `plan/bite-mount` and are do-not-merge until the Daybreak security fixes land. The open constraint is [[unit-known-limitations-arm-bite-tools]].

`scripts/orchestration_bite_suite.py` writes planner, checker, and bite rows. `scripts/gate_c_calculator.py` keeps final bite-suite rows (`passed`, `blocked`, `failed`) and drops every other suite plus `HARNESS_ERROR`. A missing bite tool is a harness error, not a Gate C sample.

## Why

Security owns `portal/platform/agent/run_loop` as its goal loop. Keeping the arm in its own module package leaves that boundary intact while the Pipeline's tool loop handles each bite.
