---
id: unit-agent-loop-discipline-borrowed-from-the-campaign-supervisor
kind: what
title: "AGENT_LOOP \u2014 Discipline (borrowed from the Campaign Supervisor)"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Discipline (borrowed from the Campaign Supervisor)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5058901
updated_at: 1784946220.5058901
---

Caps (`max_iterations`, `max_wall_clock_sec`), a confidence floor
(`flag_for_human` below it), a clean `blocked` stop when nothing is applicable,
and honest outcomes (`completed` / `blocked` / `budget_exhausted` /
`flagged_for_human` / `invalid_goal`) — never faked-green.
