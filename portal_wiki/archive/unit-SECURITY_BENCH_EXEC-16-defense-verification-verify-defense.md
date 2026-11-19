---
id: unit-SECURITY_BENCH_EXEC-16-defense-verification-verify-defense
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 16. Defense Verification (`verify_defense`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 16. Defense Verification (`verify_defense`)
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

After blue calls defensive tools (`block_ip`, `disable_account`, `revoke_tgt`), the bench probes the target to verify the action took effect:
- `block_ip` — tests if connection to the blocked IP is refused
- `disable_account` — tests if authentication with the disabled account fails
- `revoke_tgt` — checks krbtgt password age
