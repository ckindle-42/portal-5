---
id: unit-HOWTO-2-chat-with-ai
kind: why
title: "HOWTO \u2014 2. Chat with AI"
sources:
- type: code
  path: launch.sh
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/router/routing.py
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8392
updated_at: 1783195000.8392
---

**What:** Open WebUI connects to Portal Pipeline, which routes each request to the best-fit model.

**How:** Open `http://localhost:8080` and sign in with the admin credentials from `.env` — `OPENWEBUI_ADMIN_EMAIL` / `OPENWEBUI_ADMIN_PASSWORD`, the latter auto-generated on first run and printed by `launch.sh`. Open WebUI's `OPENAI_API_BASE_URL` points at the pipeline's `http://portal-pipeline:9099/v1` in `deploy/portal-5/docker-compose.yml`, so every chat flows through the router.

**Example — general chat:**
1. Select `Portal Auto Router` from the model dropdown
2. Type: `Explain how Docker networking works`
3. The `auto` workspace's `model_hint` (`huihui_ai/qwen3.5-abliterated:9b-ctx8k` in `config/portal.yaml`) selects the model served via Ollama

The `auto` workspace is special: when no explicit model is chosen, the LLM intent classifier (`_route_with_llm`, Layer 1 in `portal/platform/inference/router/routing.py`) picks the best-fit workspace, falling back to weighted keyword scoring (`_detect_workspace`, Layer 2) on low confidence or timeout. `DEFAULT_MODEL` in `.env.example` only sets Open WebUI's default picker selection.

**Verify routing:** run `./launch.sh status`, or `curl http://localhost:9099/v1/models` with `PIPELINE_API_KEY` as the bearer token.

## Why

Routing is deliberately split from serving: Open WebUI only knows one OpenAI-compatible endpoint, and the pipeline decides which workspace and model answer. Keeping the chat UI that thin means model selection, persona overrides, and tool grants can all evolve inside `config/portal.yaml` and `routing.py` without any Open WebUI change, and the two-layer classifier makes the router both accurate (LLM) and fast (keywords) without blocking the request on the classifier.
