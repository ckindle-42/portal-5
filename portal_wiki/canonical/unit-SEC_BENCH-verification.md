---
id: unit-SEC_BENCH-verification
kind: what
title: Security bench verification checklist and known issues
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- verification
created_at: 1784945480.186501
updated_at: 1784945480.186501
---

## What to Verify After Running

1. **Real execution** — Look for `[EXEC OK]` / `[EXEC ERR]` lines
2. **Real IPs** — grep for `10.10.11.21`; HTB IPs means `_sub_hint()` broken
3. **Stealth scoring** — grep for `STEALTH`
4. **Blue active response** — grep for `BLUE-ACTIVE` (with `--blue-active`)
5. **Artifact chaining** — grep for `Inherited artifacts`
6. **Lab probe** — `python3 -m portal.modules.security.core --probe-lab --dry-run`

## Known Issues

- **smbclient read-only filesystem** — Use `nxc smb` instead
- **nmap requires privileges** — NET_RAW cap added for lab-exec containers
- **Clock skew** — `_ensure_lab_time_sync()` auto-syncs before first dispatch
- **HTB IP hallucination** — `_sub_hint()` resolves `$LAB_TARGET_DC/$DOMAIN`
- **Small model exploration** — Use `--chain-rounds 3` if steps are missed
