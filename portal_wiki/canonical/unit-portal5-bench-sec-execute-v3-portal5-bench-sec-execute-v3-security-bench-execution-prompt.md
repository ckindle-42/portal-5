---
id: unit-portal5-bench-sec-execute-v3-portal5-bench-sec-execute-v3-security-bench-execution-prompt
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Security\
  \ Bench Execution Prompt"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Security Bench Execution Prompt"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.704534
updated_at: 1784946220.704534
---

> **Supersedes** `PORTAL5_BENCH_SEC_EXECUTE_V2.md` (archive to
> `docs/_archive_execdocs/`). V3 updates for the post-alias-retirement codebase
> (HEAD `87b19bf`): the pre-collapse security workspace ids (`auto-redteam`,
> `auto-blueteam`, `auto-pentest`, `auto-purpleteam*`) are **retired**. Security
> variants are now addressed canonically as **`auto-security::<variant>`**. All
> example commands and the workspace-model table are corrected. Phase 0
> lab-readiness gate, Full Expanded mode, and honeypot/hardened-twin methodology
> are retained from V2.

Run the Portal 5 security benchmark suite (`bench_security.py`, invoked via
`python3 -m portal.modules.security.core`). It evaluates security workspaces on
offensive/defensive prompts and multi-turn attack-chain tool-call sequences.
Use it to qualify new security model candidates before promoting them.

Distinct from `bench_tps.py` — TPS measures *speed*; this measures *capability*:
will the model engage offensive tasks, follow structured output, call tools in
order, complete the chain?

---
