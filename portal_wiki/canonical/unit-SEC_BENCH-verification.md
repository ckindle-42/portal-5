---
id: unit-SEC_BENCH-verification
kind: what
title: Security bench verification checklist and known issues
sources:
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/modules/security/core/commands/run.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- bench
- security
- verification
- verified-v1
created_at: 1784945480.186501
updated_at: 1784945480.186501
---

## What to Verify After Running

1. **Real execution** — the chain phase prints a per-prompt `chain(...)` summary with `exec=`, `tools=`, and `handoff=`; real dispatch yields `steps_proven`/`proven_coverage` in the result JSON rather than the `(synthetic.)` fallback marker
2. **Real IPs** — grep for `10.10.11.21`; leftover HTB IPs mean `_sub_hint()` is not substituting
3. **Stealth scoring** — grep for `[STEALTH]` lines
4. **Blue active response** — grep for `[BLUE-ACTIVE` (with `--blue-active`)
5. **Artifact chaining** — grep for `Inherited artifacts`
6. **Lab probe** — `python3 -m portal.modules.security.core --probe-lab --dry-run`

## Known Issues

- **Read-only root filesystem** — the attack image mounts a read-only root fs, so tools that must write (e.g. `smbclient`) fail inside it; the probes use `nxc smb` for SMB reachability
- **nmap requires privileges** — NET_RAW cap added for lab-exec containers
- **Clock skew** — `ensure_lab_time_sync()` auto-syncs before first dispatch
- **HTB IP hallucination** — `_sub_hint()` resolves `$LAB_TARGET_DC`/`$DOMAIN`/`$LAB_TARGET_SRV`/`$LAB_TARGET_WEB`
- **Small model exploration** — Use `--chain-rounds 3` if steps are missed

## Why

Verification matters here more than in a unit test because lab-exec results are only as trustworthy as the evidence they carry: a model can emit plausible tool calls that never reached a real target, and a synthetic fallback must never be read as a live win. The checklist therefore greps for the markers that only real dispatch produces, and the known-issues list records the failure modes that already misled people once — stale HTB IPs, clock skew, and a read-only filesystem that silently breaks certain tools.
