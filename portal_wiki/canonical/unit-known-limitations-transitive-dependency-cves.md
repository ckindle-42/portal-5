---
id: unit-known-limitations-transitive-dependency-cves
kind: what
title: Transitive DiskCache and Accelerate Advisories Are Not Reached by Untrusted Inputs
sources:
- type: code
  path: portal/modules/detection/tools/detection_mcp.py
- type: code
  path: portal/modules/research/tools/rag_mcp.py
claims:
- probe: repo.symbol.exists
  path: portal/modules/detection/tools/detection_mcp.py
  symbol: convert_sigma
  equals: true
confidence: medium
tags:
- known-limitations
- security
- dependencies

---

### Transitive DiskCache and Accelerate advisories — no untrusted input path (2026-10-21, re-verified 2026-11-19)

- **ID**: P5-DEP-CVE-001
- **Status**: NOT EXPOSED (re-verified 2026-11-19 by security sweep round 2).
- **DiskCache (PYSEC-2026-2447 / CVE-2025-69872)**: `pysigma` uses `diskcache.Cache` in its ATT&CK and D3FEND tag validators under `~/.cache/pysigma/`. The detection MCP's `convert_sigma` and `validate_sigma` routes parse with `SigmaCollection.from_yaml`; they do not invoke those validators or expose the cache path. Exploitation requires an attacker to write a pickle into the cache before the service reads it — local filesystem write access that already implies host compromise. Still no fixed release upstream: diskcache 5.6.3 remains the latest version as of 2026-11-19. Re-evaluate if the MCP invokes those validators on untrusted rules or exposes a writable cache path.
- **Accelerate (PYSEC-2026-3804 / CVE-2026-69112)**: Docling's RAG conversion accepts a document path through `DocumentConverter.convert`; the Portal route does not accept a model checkpoint or sharded index. Re-verified 2026-11-19: nothing in the installed docling 2.137 stack imports accelerate or calls the advisory's loader entry points load_checkpoint_in_model / load_checkpoint_and_dispatch (site-packages grep), so the vulnerable path is never reached. OSV still lists no fixed version (GHSA last_affected 1.14.0); accelerate 1.15.0/1.16.0 exist upstream but OSV does not mark them fixed, so the lock keeps 1.14.0 until OSV records a fix. Re-evaluate if users can supply model checkpoints or write to the model cache used by Docling.

#### Why

Both packages are installed transitively, but their vulnerable inputs are not supplied by Portal's current user-facing routes, and neither advisory has a fixed release for the sweep to move to. This boundary would change if those routes gained control over cache paths or model checkpoint indexes.
