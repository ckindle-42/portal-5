---
id: unit-SECURITY_BENCH_EXEC-smbclient-fails-with-run-samba-read-only-filesyste
kind: why
title: "SECURITY_BENCH_EXEC \u2014 smbclient fails with `/run/samba: Read-only filesystem`"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'smbclient fails with `/run/samba: Read-only filesystem`'
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.911287
updated_at: 1783195000.911287
---

Use `nxc smb` instead of `smbclient -L` for enumeration.
