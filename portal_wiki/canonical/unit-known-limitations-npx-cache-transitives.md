---
id: unit-known-limitations-npx-cache-transitives
kind: what
title: Pinned npx caches still resolve CRITICAL transitives; caches no pin launches stop being counted
sources:
- type: code
  path: scripts/security_sweep.py
claims:
- probe: repo.symbol.exists
  path: scripts/security_sweep.py
  symbol: _split_npx_caches
  equals: true
- probe: repo.symbol.exists
  path: scripts/security_sweep.py
  symbol: _npx_cache_in_use
  equals: true
confidence: high
tags:
- known-limitations
- security
- dependencies

---

- **ID**: P5-NPX-CACHE-001
- **Status**: OPEN. Recorded 2026-11-19 from the 19:20 CST sweep (`~/.portal5/security/security_sweep_20261119.md`) and a read of every cache's root `package.json` under `~/.npm/_npx`.
- **Description**: The sweep counts only the npx caches a current `config/portal.yaml` pin can launch: `_split_npx_caches` matches each cache's root dependency set against the pins' name + exact version (a floating pin matches by name), skips the rest, and the report's Inventory block lists every skipped cache with its root spec. On this host the three pins (`@modelcontextprotocol/server-filesystem@2.4.0`, `mcp-docker-server@1.0.1`, `@upstash/context7-mcp@4.7.3`) map to six caches and seven are skipped. Two pinned sources sit at the npm registry `latest` and still resolve CRITICAL transitives into their caches — `mcp-docker-server@1.0.1`: `proxy-addr 2.0.7` (GHSA-jqcg-44mw-7w3h, fixed 2.0.8) and `protobufjs 7.5.4` (GHSA-xq3m-2v4x-88gg, OSV lists 6.11.6); `@upstash/context7-mcp@4.7.3`: `proxy-addr 2.0.7` via express 5 (same GHSA). No newer upstream release exists to bump (registry `latest` equals each pin, checked 2026-11-19), so these stay open until upstream moves. Excluded from the count by the filter, recorded here so the exclusion is not silent: the two `promptfoo@^0.121.17` caches carry `mongoose 9.7.1` (GHSA-pcrw-h46h-c93h), `simple-git 3.36.0` (GHSA-x6jw-m9v5-85vh) and `@simple-git/argv-parser 1.1.1` (GHSA-v5rq-49vh-5v5c); promptfoo is the dev-only eval CLI (`pyproject.toml` dev extra), launched by an operator rather than a portal pin, so its caches leave the sweep's count with it.
- **Used by Portal**: yes — the pins are the `filesystem`, `docker` and `context7` MCP fleet services; the filter is the sweep's own inventory step.
- **Mitigation**: bump a pin when upstream publishes past the vulnerable transitives: the sweep re-counts a cache the moment a pin's name+version matches it, and the superseded cache drops out with the old pin. The promptfoo dev caches ride the dev-only eval lane; if evals ever become a production path, pin the CLI there and the same filter picks its cache up.

## Why

Round 2 pinned the npx MCP sources so a cache can be attributed to the pin that creates it, but the floating-era leftovers kept the sweep counting advisories nothing on this host launches. Matching cache to pin inside the sweep — the one mechanism that already reads the pin inventory — fixes the count without adding a prune job, and the skipped-cache listing keeps the exclusion auditable instead of hiding it.
