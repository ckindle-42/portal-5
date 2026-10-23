---
id: unit-module-orchestration
kind: mixed
title: "Orchestration Module — offline verified task runner (enabled in repo)"
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
- probe: modules.enabled
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

The orchestration module exposes `portal arm submit`, `resume`, and `status` for hand-written bite plans. Its own package lives under `portal/modules/orchestration/`; it uses the Pipeline chat endpoint and does not import or wrap `portal/platform/agent/run_loop`. A bite gets a fresh Pipeline request with the seat tag from `disciplines.<name>.seated_models` (defaulting to `auto-daily::<seat>`; the current fast seat is `auto-daily::gemma-fast`, a lineage-diverse 26B QAT choice over the Qwen fast variant). Requests carry `portal_bite_tools`, a per-request tool allowlist, a transcript, a finish requirement, and deterministic checks.

## Phase 1 boundary

Offline tests drive the arm through a fake OpenAI-compatible Pipeline API. Stored plan templates enqueue through `QueueLedger.enqueue`. Open WebUI reaches that queue through the pipeline MCP tool `arm_queue_task` (`portal/modules/orchestration/owui_entry.py`). The module is enabled in the repo since the 2026-10-23 live end-to-end run (Telegram approval, repair, review).

## Module state

The switch is `modules.orchestration.enabled` in `config/portal.yaml` and is on. The module unit documents the switch; it does not hold it. `config/orchestration_arm.yaml` supplies the default `swap` residency mode and the underlying model IDs checked by the Pipeline load guard. Seated model tags are read from `disciplines.<name>.seated_models` (fast: `auto-daily::gemma-fast`, deep: `auto-daily::deep`); the service validates the engine tag matches each seat's configured tag at startup.

## Bite tools

The worker's `portal_bite_tools` list is a per-request allowlist. `apply_bite_tool_scope` intersects Pipeline-owned tools with it and retains the client schemas the worker supplied. The worker supplies schemas for each bite's task-scoped client tools plus `finish`, dispatches those task tools locally, and sends their results into the next Pipeline turn. A Pipeline response may carry several tool calls in one turn; the worker executes all of them and each executed call counts one hop against the bite's turn budget. Requests carrying `portal_bite_tools` skip recalled-memory injection in the router (`inject_recalled_memory` returns before any recall dispatch), so a bite never pulls user memory into its context. `file_read` and `file_write` use descriptor-relative, no-follow access below the task data root. `pytest_run` puts every test file's directory on PYTHONPATH (mirroring pytest's default prepend semantics) so staged tests can import sibling modules; it sends only explicit readable and writable files into the disposable sandbox container and copies back only the write allowlist. Tool-less bites (e.g. `final_review`) receive their inputs as read-only inline snapshots in the user message so the deep seat can see the artifacts it is reviewing.

Inputs are staged under each task's `inputs/` directory using their source layout (e.g. `inputs/path/to/module.py`), so staged files can import their siblings. `file_read` and `file_write` alias the bite-prompt input names onto those staged paths so the deep seat resolves a declared input like `$source_file` to the actual file without hardcoding paths. Tool-less bites (e.g. `final_review`) receive their inputs as read-only inline snapshots in the user message so the deep seat can see the artifacts it is reviewing; the deep seat's review votes are implemented as tool-less bite requests that follow the deep seat's thinking policy. At `max_tokens=512` the deep seat spent its entire cap reasoning and returned no JSON (live 2026-10-22); the config now sets `max_tokens=8192` for review votes so the 512 token reasoning budget is not the hard wall. Budgets are per-bite in `config/orchestration_arm.yaml`: the `repair_with_tests` template's repair bite runs at 12288 output tokens and 12288 context tokens over 5 turns; its inspect bite runs at 2048 output tokens over 3 turns.

`scripts/orchestration_bite_suite.py` writes planner, checker, and bite rows. `scripts/gate_c_calculator.py` keeps final bite-suite rows (`passed`, `blocked`, `failed`) and drops every other suite plus `HARNESS_ERROR`. A missing offered tool is a harness error, not a Gate C sample.

## Why

Security owns `portal/platform/agent/run_loop` as its goal loop. Keeping the arm in its own module package leaves that boundary intact while the Pipeline's tool loop handles each bite.
