---
id: unit-known-limitations-arm-bite-tools
kind: what
title: Arm cannot run a live bite — bite tools are not implemented
sources:
- type: code
  path: portal/modules/orchestration/worker.py
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
claims: []
confidence: high
tags:
- known-limitations
- orchestration
- tools
created_at: 1792680000
updated_at: 1792680000
---

#### Arm cannot run a live bite — bite tools have no production implementation (2026-10-22)

- **ID**: P5-ARM-BITE-001
- **Status**: OPEN. Offline rigs pass. A live bite does not. Task-scoped client tools are on `plan/bite-mount` (`d5f3eca9`) and are do-not-merge until the Daybreak security fixes land.
- **Description**: The worker sends `portal_bite_tools` (the bite's names plus `finish`) and a client `tools` list that contains only the `finish` schema. `apply_bite_tool_scope` intersects that allowlist with tools the pipeline already has. It does not implement the bite tools. File read, list, search, pytest, write, and HTTP get exist in `tests/wfe/runner.py` and are not a production service. The fake pipeline used by the rig and by `scripts/orchestration_bite_suite.py --dry-run` copies `portal_bite_tools` into `tools_offered`, so an offline pass echoes the allowlist. A live trace offers only names the pipeline actually has, and the suite records `HARNESS_ERROR` when an expected bite tool is missing.
- **Gate C**: `scripts/gate_c_calculator.py` counts final bite-suite rows only (`passed`, `blocked`, `failed`, or statuses `PASS`, `BLOCKED`, `FAILED`). Planner and checker suites are skipped. `HARNESS_ERROR` is not a final state, so those rows stay in the receipt and do not enter the rates. A live suite that fails closed on missing tools therefore cannot be read as a model rate.
- **What not to do**: do not merge `plan/bite-mount` ahead of the Daybreak security fixes, and do not treat a dry-run receipt as evidence that a live bite ran.

#### Why

The request field looks like a tool mount, and the fake rig reports the allowlist as tools offered, so an offline pass reads as if the bite tools executed. They did not. Recording the gap next to the arm keeps a green rig from being taken as a license to run live bites, and it keeps a harness error out of Gate C so a missing tool is not averaged in as a model failure.
