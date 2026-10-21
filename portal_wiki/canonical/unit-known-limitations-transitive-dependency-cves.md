---
id: unit-known-limitations-transitive-dependency-cves
kind: what
title: Transitive DiskCache and Accelerate Advisories Are Not Reached by Untrusted Inputs
sources:
- type: code
  path: portal/modules/detection/tools/detection_mcp.py
- type: code
  path: portal/modules/research/tools/rag_mcp.py
claims: []
confidence: medium
tags:
- known-limitations
- security
- dependencies
created_at: 1792588377
updated_at: 1792588377
---

### Transitive DiskCache and Accelerate advisories — no untrusted input path (2026-10-21)

- **ID**: P5-DEP-CVE-001
- **Status**: NOT EXPOSED (2026-10-21).
- **DiskCache (PYSEC-2026-2447 / CVE-2025-69872)**: `pysigma` uses `diskcache.Cache` in its ATT&CK and D3FEND tag validators under `~/.cache/pysigma/`. The detection MCP's `convert_sigma` and `validate_sigma` routes parse with `SigmaCollection.from_yaml`; they do not invoke those validators or expose the cache path. Exploitation requires an attacker to write a pickle into the cache before the service reads it. Re-evaluate if the MCP invokes those validators on untrusted rules or exposes a writable cache path.
- **Accelerate (PYSEC-2026-3804 / CVE-2026-69112)**: Docling's RAG conversion accepts a document path through `DocumentConverter.convert`; the Portal route does not accept a model checkpoint or sharded index. Exploitation requires a malicious checkpoint weight map consumed by the upstream loader functions load_checkpoint_in_model or load_checkpoint_and_dispatch. Re-evaluate if users can supply model checkpoints or write to the model cache used by Docling.

#### Why

Both packages are installed transitively, but their vulnerable inputs are not supplied by Portal's current user-facing routes. This boundary would change if those routes gained control over cache paths or model checkpoint indexes.
