---
id: unit-performance-keyword-cache
kind: what
title: "PERFORMANCE \u2014 Keyword Cache"
sources:
- type: code
  path: portal/platform/inference/router/routing.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.509892
updated_at: 1784946220.509892
---

The Layer-2 keyword scorer (`_detect_workspace` in `portal/platform/inference/router/routing.py`) ranks the last user message against per-workspace keyword dictionaries. At module import time the router pre-compiles every workspace's keyword dict to lowercase into the module-level `_KEYWORD_CACHE`, a `{workspace_id: {keyword: weight}}` map.

At request time the scorer lowercases the user message exactly once, then for each cached workspace sums the weights of keywords found in that text and keeps the workspaces whose score clears their configured `threshold`. The cache eliminates the two per-request costs a naive implementation would pay: a `.lower()` per keyword (tens of keyword strings per workspace) and a rebuild of each keyword dict on every request.

## Why

The keyword scorer runs on the fallback path of every request the LLM router cannot confidently classify, so its steady-state cost is paid whether or not routing succeeds. Pre-lowering the keywords at import time moves an O(keywords) transformation off the hot path, leaving each request with one lowercase pass over the user text and a bounded set of substring checks. The invariant this cache protects is that keyword fallback stays cheap enough to run on every uncertain request without becoming a measurable latency item.
