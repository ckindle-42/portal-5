---
id: unit-readme-then-free-disk-space-and-retry-launch-sh-up
kind: what
title: "README \u2014 Then free disk space and retry ./launch.sh up"
sources:
- type: code
  path: scripts/lib/util.sh
- type: code
  path: launch.sh
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.688473
updated_at: 1784946220.688473
---

The disk check in `_check_hardware` (`scripts/lib/util.sh`) is the first-run
gating constraint: below 20 GB free it warns and suggests `docker system prune -a`
before continuing, and below 50 GB it notes that more is needed for the full
model catalog. Because the core models plus the FLUX checkpoint (~12 GB) are the
bulk of a first download, a tight disk makes `up` or the model pulls fail
mid-transfer, so the remediation is to free space and re-run `./launch.sh up`.

If models are not loading and Ollama reports zero backends, ensure at least one
model is pulled:

```bash
./launch.sh pull-models     # Ensure at least one model is pulled
```

## Why

Disk is checked before any pull because a failed multi-gigabyte download is the
most wasteful failure mode — the download restarts or half-completes, and the
stack comes up without usable models. Gating on free space up front, and offering
the exact prune command, turns a storage shortfall into a quick fix rather than a
confusing mid-boot error.
