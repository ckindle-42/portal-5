---
id: unit-SECURITY_BENCH_EXEC-3-blue-active-response
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 3. Blue Active Response"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 3. Blue Active Response
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

When `--blue-active` is used, the blue defender model can call defensive tools that execute in the lab:
- `block_ip(ip)` — adds firewall rule on the DC
- `disable_account(username)` — disables a compromised AD user
- `revoke_tgt(domain)` — purges Kerberos tickets on the DC

Results appear as `[BLUE-ACTIVE OK]` / `[BLUE-ACTIVE ERR]` in the output.
