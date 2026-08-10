---
id: unit-known-limitations-serena-gate-d1-airgap-staging
kind: what
title: "KNOWN_LIMITATIONS \u2014 Serena GATE-D1 air-gap LSP staging"
sources:
- type: code
  path: config/portal.yaml
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786309400.0
updated_at: 1786309400.0
---

- **ID**: P5-SERENA-GATE-D1
- **Status**: Not applicable on this box; deferred as a note for a genuinely air-gapped
  deployment. TASK-BATCH-BENCH-001 Part D finding.
- **Description**: The `serena` `mcp_fleet` entry (`config/portal.yaml`) launches via
  `uvx --from git+https://github.com/oraios/serena serena start-mcp-server`, which fetches the
  Serena package from GitHub and its LSP backend (`pyright`, via a further `uvx pyright==1.1.403`
  invocation) from PyPI on first activation. TASK-BATCH-BENCH-001's GATE-D1 flagged this as a
  potential blocker on an air-gapped box, where these must be pre-staged rather than fetched live.
  This box has live internet access throughout the whole batch-bench session (confirmed by ~60GB
  of HuggingFace model pulls across Parts A-C) — `uvx` fetched and built `serena-agent` plus
  `pyright-langserver` cleanly on first `activate_project` call (see
  `results/serena_refactor_bench_20260809.md`), so GATE-D1 did not block anything here.
- **For an actual air-gapped deployment**: pre-stage the `oraios/serena` package (e.g. a vendored
  wheel or mirrored pip index) and a `pyright` binary matching the pinned `1.1.403` version (or
  configure Serena's `--language-backend` for an alternative already-installed language server),
  then confirm `uvx --from git+https://github.com/oraios/serena serena start-mcp-server --help`
  succeeds with network access disabled before relying on the fleet entry in production.

## Why

Recording that GATE-D1 was checked and found not-applicable — rather than silently skipping the check because it happened to not matter — is what keeps this a real gate for any future deployment of this fleet entry onto hardware that isn't already known to have live internet, instead of an assumption nobody re-verifies.
