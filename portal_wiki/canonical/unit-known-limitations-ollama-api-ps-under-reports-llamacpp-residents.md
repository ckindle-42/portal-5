---
id: unit-known-limitations-ollama-api-ps-under-reports-llamacpp-residents
kind: what
title: Ollama 0.40 /api/ps Under-Reports llamacpp-Runner Residents
sources:
- type: code
  path: portal/platform/inference/load_guard.py
claims: []
confidence: high
tags:
- known-limitations
- ollama
- memory
created_at: 1792540800
updated_at: 1792540800
---

#### Ollama 0.40 `/api/ps` under-reports llamacpp-runner residents — the load guard unloads to measure (2026-10-21)

- **ID**: P5-LOADGUARD-PS-001
- **Description**: Ollama 0.40's llamacpp runner reports a resident model's `/api/ps` size from less than its `llama-server` child actually holds: `devstral-small-2` (24B Q4) reported **1.8 GB** while the child process held **~15 GB** RSS (measured 2026-10-21). The load guard builds host headroom as oMLX's ceiling minus its residents, plus idle Ollama residents at their reported size, so an idle resident that under-reports is credited with a fraction of the memory it would release.
- **Impact**: A cold load could wait out its full deadline (120 s) and then refuse with HTTP 507 for memory Ollama frees on load. On 2026-10-21, 9 of 54 engine-UAT shots did exactly that.
- **Mitigation**: When a shortfall survives the oMLX pass, `LoadGuard._free_ollama` unloads every idle, unpinned, unprotected, not-busy Ollama resident with `keep_alive: 0` and re-measures through oMLX's ceiling, which sees the freed bytes even though `/api/ps` never counted them. Busy models are never unloaded; with nothing in flight and nothing idle left to free, admission refuses at once instead of waiting out the deadline.

#### Why

The reported size is engine bookkeeping, not an accounting of the child process, so trusting it made the guard wait for memory it could have freed itself. Unloading makes oMLX's ceiling the measurement authority — the host sees bytes the model scheduler does not — at the cost of a cold load for whoever asks for that model next, which is why only idle, unpinned, unprotected residents are candidates.
