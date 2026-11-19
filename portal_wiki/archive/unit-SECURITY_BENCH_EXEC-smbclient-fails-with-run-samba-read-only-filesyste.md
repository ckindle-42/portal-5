---
id: unit-SECURITY_BENCH_EXEC-smbclient-fails-with-run-samba-read-only-filesyste
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 smbclient fails with `/run/samba: Read-only filesystem`"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'smbclient fails with `/run/samba: Read-only filesystem`'
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

Use `nxc smb` instead of `smbclient -L` for enumeration.
