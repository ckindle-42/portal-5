---
id: unit-surface-uat
kind: mixed
title: "UAT driver library \u2014 modularized live-stack acceptance runner"
sources:
- type: code
  path: tests/uat/*.py
- type: code
  path: tests/uat/adaptive/*.py
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785886800.0
updated_at: 1785886800.0
---

The UAT driver library is the modularised live-stack acceptance runner: it drives requests into Open WebUI through the portal pipeline, grades each response, and reports the outcome.

## Why

The driver proves the live stack serves each persona section correctly, so its modules split into orchestration and evaluation. Keeping sequencing in the runner while dispatch, grading, and routing live in their own modules means a failed run is attributable to one stage. The split isolates the distinctive contracts: dispatch must raise `_PresetUnreachableError` distinctly so a swallowed unreachable preset never reports a silent no-op as a pass, and routing must resolve an unmapped slug to itself without crashing.

## Interfaces

Entry and orchestration: the CLI selects sections and run modes, the runner walks sections applying skip rules, and the monitor reports progress. Stack drivers: browser drives Playwright login and completion-wait; freshness blocks on stale images versus git HEAD. Evaluation: grading validates response and heavy artifact formats; calibration normalises raw scores; routing maps a persona slug to its expected workspace. Notifications: notify sends the completion signal with the `_git_sha` it needs for audit.

## Gotchas

The runner drives real Open WebUI — a live acceptance run, not a unit test — so stale images must block, not warn. The monitor must not mutate the run state it reports. Heavy format validators import lazily; an absent format cannot crash the run. Eager skip rules hide failures.

## Adaptive layer

`tests/uat/adaptive/` sits above the keyword catalog: it introspects each OWUI-addressable space's declared contract from config, has an independent agent author deep intended-use challenges across seven dimensions, executes them through the same browser runner via `--adaptive` (a catalog swap in `_select_tests` — nothing downstream changes), and rolls results up capability-by-capability behind an operator `[GATE]`. It is additive; the keyword catalog is untouched and stays the fast regression layer.
