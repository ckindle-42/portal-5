---
id: unit-HOWTO-supported-formats
historical: true
kind: why
title: "HOWTO \u2014 Supported formats"
sources:
- type: design
  path: docs/HOWTO.md
  section: Supported formats
confidence: high
tags:
- docs
- HOWTO

---


PDF (with image extraction), DOCX, TXT, Markdown, CSV, HTML

**How it works:** Documents are chunked into 1500-char segments with 100-char overlap, embedded using `microsoft/harrier-oss-v1-0.6b` (served by portal5-embedding TEI container on :8917), and searched with hybrid mode (semantic + keyword). Results are reranked by `bge-reranker-v2-m3` cross-encoder.

**Verify:**
```bash
