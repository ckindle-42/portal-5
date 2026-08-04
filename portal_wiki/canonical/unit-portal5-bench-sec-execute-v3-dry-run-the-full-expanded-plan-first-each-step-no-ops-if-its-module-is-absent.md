---
id: unit-portal5-bench-sec-execute-v3-dry-run-the-full-expanded-plan-first-each-step-no-ops-if-its-module-is-absent
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Dry-run the full expanded plan first (each\
  \ step no-ops if its module is absent)"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/bench_integration.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.7083
updated_at: 1784946220.7083
---

```bash
python3 -m portal.modules.security.core --full-expanded --dry-run
```

`--full-expanded` (defined in `cli.py`) adds the security expansion steps on top
of the workspace bench: the named-oracle count, the CTF flag-oracle bench, the
OWASP LLM-redteam probes, the validation suite's Log4Shell
vulnerable-vs-hardened use-case, and a field-journal write. Each expansion step
wraps its module import in a try/except and prints "module absent — skipped"
when the module cannot be imported, so a partial install degrades gracefully.
`--dry-run` stops every step before live inference: workspace rows print
"DRY-RUN", the CTF and LLM-redteam steps short-circuit, and the journal write is
skipped. Note that `bench_integration.run_full_expanded_bench` is a separate
loader exercised by tests, not the code path `cli.py`'s flag invokes.

## Why

A full-expanded run is multi-hour and lab-touching, so dry-running first is the
only cheap way to confirm every step resolves before committing real time. The
per-step ImportError fallback is intentional: the suite must never crash on a
box that lacks one optional module, and it must say so explicitly when one is
missing.
