---
id: unit-portal5-bench-sec-execute-v3-portal5-bench-sec-execute-v3-security-bench-execution-prompt
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Security\
  \ Bench Execution Prompt"
sources:
- type: code
  path: tests/benchmarks/bench_security.py
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/__main__.py
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: config/portal.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.704534
updated_at: 1784946220.704534
---

Supersedes the V2 execute prompt, archived at
`docs/_archive_execdocs/PORTAL5_BENCH_SEC_EXECUTE_V2.md`. V3 reflects the
post-alias-retirement codebase: the pre-collapse security workspace ids
(`auto-redteam`, `auto-blueteam`, `auto-pentest`, `auto-purpleteam*`) are
retired, and security variants are addressed canonically as
`auto-security::<variant>`. `scripts/execute_preflight.py` enumerates the live
variant set from `config/portal.yaml` and fails loudly if any retired alias
leaks back into the workspace table.

The suite is `tests/benchmarks/bench_security.py`, a thin re-export shim whose
implementation lives under `portal/modules/security/core/`; the real entry
point is `python3 -m portal.modules.security.core` (`__main__.py` dispatches to
`cli.main`). It evaluates security workspaces on offensive/defensive prompts
(the tool-free theory pass) and, for the execution workspaces, on multi-turn
attack-chain tool-call sequences. This is capability measurement and is
distinct from `tests/benchmarks/bench_tps.py`, which measures throughput:
will the model engage offensive tasks, follow structured output, call tools in
order, and complete the chain?

## Why

The collapse folded nine discipline workspaces into one `auto-security` base
with config-driven variants, so every example command in the earlier prompt
was stale and a bare `auto-pentest` target would fail. Grounding the runbook to
`cli.py` and `scripts/execute_preflight.py` keeps the invocation aligned with
the code that actually executes the bench, instead of a snapshot from a dated
document.

---
