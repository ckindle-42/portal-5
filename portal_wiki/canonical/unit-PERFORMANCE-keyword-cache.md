---
id: unit-PERFORMANCE-keyword-cache
kind: why
title: "PERFORMANCE \u2014 Keyword Cache"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: Keyword Cache
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.880596
updated_at: 1783195000.880596
---

Workspace keyword dictionaries are pre-compiled to lowercase at module load (`_KEYWORD_CACHE`). Eliminates repeated `.lower()` calls and dict rebuilding on every request.
