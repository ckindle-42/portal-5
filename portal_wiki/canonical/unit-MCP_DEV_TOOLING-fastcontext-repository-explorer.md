---
id: unit-MCP_DEV_TOOLING-fastcontext-repository-explorer
kind: why
title: "MCP_DEV_TOOLING \u2014 FastContext Repository Explorer"
sources:
- type: design
  path: docs/MCP_DEV_TOOLING.md
  section: FastContext Repository Explorer
last_generated_commit: ''
confidence: high
tags:
- docs
- MCP_DEV_TOOLING
created_at: 1783195000.871671
updated_at: 1783195000.871671
---


`explore_repository(query)` runs **FastContext-1.0-4B-SFT** (Microsoft, 2.5 GB,
[arxiv:2606.14066](https://arxiv.org/abs/2606.14066)) as a dedicated repository exploration subagent.

Instead of the main coding model burning its token budget scanning files, FastContext:
1. Receives the query (`"where is SSE streaming implemented"`)
2. Issues parallel `READ` / `GLOB` / `GREP` tool calls across the repo
3. Returns compact `{path, start_line, end_line, note}` citations

**Why it matters:** On SWE-bench benchmarks, FastContext reduces the main agent's token
consumption by 50–60% while improving resolution rates by up to 5.5 points. In practice:
Devstral reads 3 targeted file ranges instead of exploring blindly.

```json
{
  "citations": [
    {
      "path": "portal_pipeline/router/streaming.py",
      "start_line": 45, "end_line": 120,
      "note": "SSE streaming loop, tool call dispatch, preamble injection"
    },
    {
      "path": "portal_pipeline/router_pipe.py",
      "start_line": 230, "end_line": 280,
      "note": "lifespan, route registration, stream endpoint"
    }
  ],
  "turns_used": 2,
  "model": "hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M"
}
```

**Model must be pulled first:**

```bash
ollama pull hf.co/mitkox/FastContext-1.0-4B-SFT-Q4_K_M-GGUF:Q4_K_M
```

---
