---
id: unit-V2_SCENARIO_AUDIT_V1-5-linux-terminal-stateful-vs-uat-p-d12
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 5. `linux-terminal-stateful` vs UAT P-D12"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: 5. `linux-terminal-stateful` vs UAT P-D12
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.9238
updated_at: 1783195000.9238
---


**UAT P-D12 status**: FAIL (2/4 with Laguna)
**V2 Laguna result**: PASS

**UAT prompt** (verbatim from line 3561-3566):
> $ mkdir -p /tmp/portal_test && cd /tmp/portal_test
> $ echo "hello portal" > greet.txt
> $ cat greet.txt
> $ pwd

**V2 prompt** (verbatim from coding_scenarios.yaml):
> You are a Linux terminal. Execute these commands in sequence,
> preserving working-directory and file-system state between them.
> Show only the terminal output for each command — no prose, no code
> blocks, just what the terminal would print.
>
> $ mkdir -p /tmp/portal_test
> $ cd /tmp/portal_test
> $ echo "hello portal" > greeting.txt
> $ cat greeting.txt
> $ pwd
> $ ls -la

**Axis scores**:
- Output-format prescription: **Y** — V2: "Show only the terminal output for each command — no prose, no code blocks, just what the terminal would print." and "preserving working-directory and file-system state between them." UAT: chained shell commands with no format guidance; the `$` prefix is implicit terminal framing.
- Required-element naming: **N** — V2 assertion elements ("hello portal", "/tmp/portal_test", "greeting.txt") are natural outputs of the provided commands. V2 does not name them as explicit requirements separate from the commands themselves.
- Algorithm prescription: **N** — No algorithm prescribed. The commands differ slightly (greet.txt vs greeting.txt, added ls -la) but these are task-content differences, not approach prescriptions.

**Verdict**: MIXED

**Notes**: V2's "preserving working-directory and file-system state" explicitly instructs the model to maintain state — exactly what Laguna failed at in UAT (lost cwd between commands). The UAT placed this burden on the persona's system prompt. V2's "no prose, no code blocks" also addresses the prose-output failure mode.

---
