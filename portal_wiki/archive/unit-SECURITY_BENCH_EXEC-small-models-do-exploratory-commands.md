---
id: unit-SECURITY_BENCH_EXEC-small-models-do-exploratory-commands
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Small models do exploratory commands"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Small models do exploratory commands
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.912203
updated_at: 1783195000.912203
---

- Tool_hint shows exact command with real IPs
- Retry directive shows exact JSON tool call format
- `fallback_techniques` provide alternative commands on round 2+
- Consider `--chain-rounds 3` if steps are missed

---
