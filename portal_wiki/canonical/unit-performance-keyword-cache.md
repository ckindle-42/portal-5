---
id: unit-performance-keyword-cache
kind: what
title: "PERFORMANCE \u2014 Keyword Cache"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: Keyword Cache
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.509892
updated_at: 1784946220.509892
---

Workspace keyword dictionaries are pre-compiled to lowercase at module load (`_KEYWORD_CACHE`). Eliminates repeated `.lower()` calls and dict rebuilding on every request.
