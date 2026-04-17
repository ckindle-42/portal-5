# Portal 5 Acceptance Test Results — V6

**Date:** 2026-04-17 03:34:29
**Git SHA:** 79c2053
**Sections:** S0, S1, S2, S12, S13, S40
**Runtime:** 15s (0m 15s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 38 |
| **Total** | **38** |

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.4 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.2s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: 79c2053 | 0.0s |
| S0 | S0-06 | MLX watchdog not running | ✅ PASS | watchdog not running | 0.0s |
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 7 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 17 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 45 personas | 0.0s |
| S1 | S1-05 | Persona count | ✅ PASS | 45 personas (expected ~45) | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 19 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models in VLM_MODELS (m | ✅ PASS | ✓ Gemma 4 31B + E4B + JANG in VLM_MODELS | 0.0s |
| S1 | S1-09 | MLX routing: text-only models NOT in VLM | ✅ PASS | ✓ Magistral + Phi-4 use mlx_lm | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ✅ PASS | all 45 personas use valid workspace_model values | 0.0s |
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 0.7s |
| S2 | S2-02 | Pipeline /health | ✅ PASS | backends=7/7, workspaces=17 | 0.0s |
| S2 | S2-03 | Ollama | ✅ PASS | 24 models | 0.0s |
| S2 | S2-04 | Open WebUI | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-05 | SearXNG | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-06 | Prometheus | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-07 | Grafana | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-08 | MCP documents (:8913) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-09 | MCP music (:8912) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-10 | MCP tts (:8916) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-11 | MCP whisper (:8915) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-12 | MCP sandbox (:8914) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-13 | MCP video (:8911) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-14 | MCP embedding (:8917) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-15 | MLX proxy | ✅ PASS | state=ready | 0.0s |
| S2 | S2-16 | MLX Speech | ✅ PASS | HTTP 200 | 0.0s |
| S12 | S12-01 | SearXNG search | ✅ PASS | 32 results | 1.2s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.8s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 905 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 3/5 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |