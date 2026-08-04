---
id: unit-known-limitations-p5-emergent-002-deterministic-capability-ranker-can-t-reach-oracle-bearing-capabilities-once-any-tool-declaring-recon-capability-is-a-candidate
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-EMERGENT-002 \u2014 Deterministic capability progression\
  \ (Resolved)"
sources:
- type: code
  path: portal/platform/agent/decide.py
- type: code
  path: portal/platform/agent/tests/test_agent_core.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/objective_executor.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.676039
updated_at: 1784946220.676039
---

**Status:** RESOLVED 2026-07-29.

Found live during `TASK_SECURITY_ARM_CLOSE_LOOP_V1` Phase 8 (`goal emergent`
against `10.10.11.50`, `objective_class=host_foothold`, 2026-07-16). The
deterministic fallback selected a tool before selecting a capability, so any
tool-declaring reconnaissance candidate made `tools=[]` exploit capabilities
with real oracles structurally unreachable. It also ignored action history,
reselected the same reconnaissance action, and eventually hit the I4
no-progress gate.

Two real, separate fixes are already applied in this task's run (both
correctness fixes, not workarounds): (1) `SecurityExecutor.execute` now
dispatches on `decision["action"]` (the semantic capability id) instead of
`decision["tool"]` (the raw binary name) — `lab.lab_dispatch`'s fn_name
routing is action-keyed, so dispatching on `tool` silently fell through to
the synthetic catch-all the moment any capability had a declared tool; (2)
`lab.py`'s `run_nmap_scan`/`nmap` fixed port list only covered AD-lab ports
and missed the WEB target's own vulhub ports (6379/8081/8983) — perception
never discovered those services even though they're live.

The platform-level cause is now fixed in
`portal/platform/agent/decide.py`. The fallback:

1. reads both platform-loop and direct-decision history shapes;
2. selects a grounded capability before ranking tools within it;
3. starts with reconnaissance when appropriate;
4. avoids repeating attempted capabilities while alternatives remain;
5. progresses after reconnaissance to an oracle-bearing or other non-recon
   capability; and
6. can select a grounded `tools=[]` capability directly.

Regression coverage in
`portal/platform/agent/tests/test_agent_core.py` proves initial
reconnaissance, progression to an oracle-bearing action, and direct-history
compatibility. The full local CI mirror and system validator pass. This
resolves the deterministic reachability defect; live target availability and
the separately documented unverified tool-alias gap remain independent
operational constraints.

## Why

The deterministic ranker must pick a capability before ranking its tools, because dispatch is capability-keyed and a tool-first choice structurally starves every `tools=[]` oracle-bearing option. Progressing from recon to an unattempted oracle-bound action is what makes the loop truthful — it can reach the capability that actually proves the objective — and the regression tests in `test_agent_core.py` pin that ordering so a future refactor cannot silently reintroduce the dead-end.
