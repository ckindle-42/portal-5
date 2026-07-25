---
id: unit-known-limitations-importing-the-security-bench-module-sets-a-linux-only-prometheus-multiproc-dir-host-side
kind: what
title: "KNOWN_LIMITATIONS \u2014 Importing the security bench module sets a Linux-only\
  \ PROMETHEUS_MULTIPROC_DIR host-side"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Importing the security bench module sets a Linux-only PROMETHEUS_MULTIPROC_DIR
    host-side
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.671319
updated_at: 1784946220.671319
---

- **ID**: P5-ENV-MULTIPROC-HOSTLEAK-001
- **Description**: `tests/benchmarks/bench_lab_exec.py` has a module-level
  `_load_env()` call that runs `os.environ.setdefault(k, v)` for every line
  in `.env` **at import time**, unconditionally. `portal/modules/security/
  core/_data.py` imports `bench_lab_exec` at its own module level, so simply
  importing anything under `portal.modules.security.core` (e.g.
  `from portal.modules.security.core._data import PER_WORKSPACE_TIMEOUT`)
  copies `.env`'s `PROMETHEUS_MULTIPROC_DIR=/dev/shm/portal_metrics` (a
  path that only exists inside the Linux Docker containers) into the
  process environment on the host. On macOS (no `/dev/shm`), any
  subsequent code that imports `portal.platform.inference.router.metrics`
  in the same process — including this security module's own
  `preinject`/`routing` imports — then crashes with
  `FileNotFoundError: /dev/shm/portal_metrics/gauge_all_<pid>.db`
  (prometheus_client's `Gauge.__init__` tries to mmap a file there).
  Reproduced live while verifying `CLOSEOUT_ALIAS_REMOVAL.md` Holdout 3's
  `DEFAULT_WORKSPACES`/`PER_WORKSPACE_TIMEOUT` canonicalization.
- **Impact**: any host-native (non-Docker) Python process that imports both
  the security bench module and the pipeline's metrics module in the same
  interpreter — `scripts/validate_system.py`'s AU/AV checks worked around
  this by stripping the var before their subprocess calls (see their code
  comments); this is likely also implicated in the `ci_local.sh` hang
  flagged earlier in this session (`pytest tests/unit portal/modules/
  security/tests` in a fresh venv) — worth checking first if that's
  revisited.
- **Not fixed here**: out of scope for the alias-closeout work. The real
  fix is either making `bench_lab_exec.py` not mutate global env as an
  import-time side effect, or making the multiprocess dir path OS-aware
  (e.g. `tempfile.gettempdir()`-based) rather than hardcoding a Linux path
  in `.env`.
