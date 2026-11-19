---
id: unit-claude-surgical-changes
historical: true
kind: why
title: "CLAUDE.md \u2014 Surgical Changes"
sources:
- type: design
  path: CLAUDE.md
  section: Surgical Changes
confidence: high
tags:
- claude
- architecture
- law

---


**Touch only what you must. Clean up only your own mess.**

- Every changed line should trace directly to the task. Don't "improve" adjacent code, comments, or formatting; match existing style even where you'd choose differently.
- Remove imports/variables/functions that YOUR change made unused. Pre-existing dead code: mention it, don't delete it unless asked.
- Before staging, confirm the diff contains no ride-along artifacts (see Testing Rules on `field_journal/` write-through).
