---
id: unit-portal5-bench-sec-execute-v3-autonomous-monitoring-loop-required-default
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Autonomous Monitoring Loop \u2014 required\
  \ default"
sources:
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/__init__.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.706641
updated_at: 1784946220.706641
---

Security chains are slow by construction: thinking models plus tool
round-trips, with `_data.py`'s `PER_WORKSPACE_TIMEOUT` capping per-workspace
requests at up to 1500 seconds for the `auto-security::redteam`,
`auto-security::purpleteam`, and `auto-security::purpleteam-deep` keys, and
`CHAIN_MODEL_TURN_TIMEOUT_S` aborting a single model turn at 300 seconds. A
full multi-variant run therefore spans hours. The execute agent should
establish a periodic monitoring loop after launch — the same wakeup pattern the
TPS and acceptance execute prompts use — checking liveness and progress roughly
every 20 to 30 minutes, skipping and noting a hung workspace, and halting with
evidence if the whole run has stalled. This is operator process guidance, not a
harness feature: nothing in the bench code schedules wakeups on the operator's
behalf.

## Why

Idle-timeout caps and per-turn aborts make the harness fail-safe, but they do
not tell a long unattended run to keep going or when to give up. The monitoring
loop is the human-in-the-loop complement to those mechanical timeouts,
converting a silent multi-hour stall into an observed, recorded decision instead
of burned compute.

---
