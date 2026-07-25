---
id: unit-known-limitations-hunter-budget-can-starve-the-expert-entirely
kind: what
title: "KNOWN_LIMITATIONS — Hunter Round Budget Can Starve the Expert Entirely"
sources:
- type: code
  path: portal/modules/security/core/blue_orchestrate.py
  commit: cd305024
  section: _run_three_section
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
  commit: 89885284
last_generated_commit: 89885284
confidence: high
tags:
- docs
- security
created_at: 1784952000.0
updated_at: 1784952000.0
---

- **ID**: P5-SEC-BUDGET-STARVE-001
- **Description**: `_run_three_section`'s hunt loop breaks out with no verdict the moment
  the round budget is exhausted WHILE the Hunter still wants more evidence and hasn't yet
  hit the stall cap (`if hunter_out.wants_more() and not stalled: if _budget_exhausted():
  break`) — this exits the function without ever calling the Expert. This is pre-existing
  V2 behavior (`max_rounds` always worked this way), but V3B's `budgets={"hunter": N}`
  kwarg makes it trivial to configure a value tight enough to hit this every time: each
  no-hypothesis round costs 2 of the round budget (one for the Hunter call, one for the
  tool gather that follows it), so `hunter_budget=4` only affords 2 full hunt cycles —
  never enough to reach the stall cap (3 consecutive no-hypothesis rounds needs ~5-6
  rounds), and V3A's Mentor makes this worse, not better: a successful Mentor
  intervention resets the consecutive-no-hypothesis counter (by design — it's meant to
  give the Hunter a genuine fresh shot), which means reaching the stall cap under Mentor
  needs even more round budget than without it, not less.
- **Impact**: Found live 2026-07-25 (corpus-replay V3 validation bench, first full
  51-cell sweep): `budgets={"hunter": 4, "expert": 2}` produced 14/17 UNRESOLVED results
  that all shared the identical signature — `rounds=4`, trace ending right after the 2nd
  tool gather, `wants_more=True` on the last Hunter turn, Expert never invoked. Raising to
  `hunter=10` (orchestrated) / `hunter=8` (council) fixed most of these, but even
  `hunter=8` in council mode was still occasionally insufficient once Mentor fired and
  reset the counter (see corpus_replay_bench.py commit 89885284's changelog). Any
  operator or bench author using `budgets=` should not assume the round count they pass
  maps 1:1 to "number of Hunter turns" — it maps to total round increments across
  Hunter+tool+Mentor+Expert combined, and Mentor's own reset behavior consumes more of
  that budget than the un-mentored case.
- **Operator action**: When configuring `budgets["hunter"]`, budget for at minimum
  `2 * (stall_cap + mentor_max_invocations)` rounds (with V2 defaults, stall_cap=3,
  mentor_max_invocations=2 → at least 10) to give the loop a real chance to either
  converge or reach the stall-cap handoff to the Expert. A lower budget is a legitimate
  choice for a deliberately fast/cheap probe, but the caller should expect a high
  UNRESOLVED rate as the direct, mechanical consequence of that choice — not a signal
  about model capability.
