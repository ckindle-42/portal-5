# Portal 5 Acceptance Test Results — V6

**Date:** 2026-06-26 17:16:17
**Git SHA:** 592fc61
**Sections:** S1, S17, S41, S60, S70
**Runtime:** 29s (0m 29s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 38 |
| ❌ FAIL | 1 |
| ⚠️  WARN | 5 |
| ℹ️  INFO | 2 |
| **Total** | **46** |

**Code defects: 0 · Env issues: 0 · Unclassified: 6**

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 6 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 90 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 130 personas | 0.1s |
| S1 | S1-05 | Persona count matches yaml file count | ✅ PASS | 130 loaded, 130 yaml files | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 31 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-09 | MLX routing: text-only models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ✅ PASS | all 130 personas use valid workspace_model values | 0.0s |
| S1 | S1-11 | All personas have PERSONA_PROMPTS entrie | ❌ FAIL | missing prompts for: ['bench-glm', 'bench-glm-reap', 'bench-glm-z1-rumination',  | 0.0s |
| S1 | S1-17 | workspace hint reachability | ✅ PASS | all 90 workspace hints resolve | 0.1s |
| S17 | S17-01 | CAD render MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S17 | S17-02 | Tools manifest — render_mesh / render_op | ✅ PASS | found: ['convert_cad', 'render_mesh', 'render_openscad'] | 0.0s |
| S17 | S17-03 | render_mesh — 20×10×5 box → PNG + bbox | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/render_fe366668.png",
  "png_url" | 0.2s |
| S17 | S17-04-pre | (internal) render_mesh for URL check | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/render_46f3bb5a.png",
  "png_url" | 0.0s |
| S17 | S17-04 | render_mesh PNG URL reachable via HTTP | ✅ PASS | GET http://localhost:8926/files/models3d/render_46f3bb5a.png → 200 | 0.0s |
| S17 | S17-05 | render_openscad — hollow box SCAD → PNG | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/model_0f0a7bef.png",
  "png_url": | 0.2s |
| S17 | S17-06 | render_openscad — sphere primitive | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/model_0016e8f1.png",
  "png_url": | 0.1s |
| S17 | S17-07 | convert_cad — STL → OBJ | ✅ PASS | {
  "output_path": "/workspace/generated/models3d/s17_smoke_box_615697.obj",
  " | 0.0s |
| S17 | S17-08 | convert_cad — STL → PLY | ✅ PASS | {
  "output_path": "/workspace/generated/models3d/s17_smoke_box_f9b22a.ply",
  " | 0.0s |
| S17 | S17-09 | render_mesh — STL recognised (regression | ✅ PASS | {
  "png_path": "/workspace/generated/models3d/render_5edbf046.png",
  "png_url" | 0.0s |
| S17 | S17-10 | auto-cad workspace — pipeline accepts re | ✅ PASS | HTTP 200 | 16.3s |
| S41 | S41-01 | /health/all aggregator | ✅ PASS | 12/16 services ok: pipeline, ollama, mcp_comfyui, mcp_video, mcp_music | 0.1s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-e2b-pentest limit=5, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-1p2b limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-230m limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-350m limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-03 | /admin/refresh-tools | ✅ PASS | 49 tools registered | 0.0s |
| S41 | S41-04 | Power metrics in /metrics | ✅ PASS | portal5_power_* and portal5_energy_* present | 0.0s |
| S41 | S41-05 | Workspace consistency | ✅ PASS | 90 workspaces, pipe+yaml match | 0.0s |
| S60 | S60-01 | Tool registry loaded | ✅ PASS | 0 tools: ... | 0.0s |
| S60 | S60-02 | Workspace tool whitelists | ✅ PASS | 36/90 workspaces have tools | 0.0s |
| S60 | S60-03 | Persona tool resolution | ✅ PASS | tools_allow override works: ['execute_python'] | 0.0s |
| S60 | S60-04 | Tool dispatch function | ✅ PASS | exists | 0.0s |
| S60 | S60-05 | MAX_TOOL_HOPS | ✅ PASS | value=20 | 0.0s |
| S60 | S60-06 | Tool-call Prometheus metrics | ⚠️  WARN | some tool metrics missing  [UNCLASSIFIED] | 0.0s |
| S60 | S60-07 | agentorchestrator persona | ✅ PASS | slug=agentorchestrator, workspace=auto-agentic | 0.0s |
| S70 | S70-01 | SearXNG web search | ✅ PASS | 34 results returned | 0.8s |
| S70 | S70-02 | Research MCP health | ✅ PASS | {"status":"ok","service":"research-mcp","backend":"searxng"} | 0.0s |
| S70 | S70-03 | Memory MCP health | ✅ PASS | {"status":"ok","service":"memory-mcp","stored":16} | 0.0s |
| S70 | S70-04 | RAG MCP health | ✅ PASS | {"status":"ok","service":"rag-mcp","knowledge_bases":[]} | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ✅ PASS | tools: ['web_search', 'web_fetch', 'news_search', 'kb_search', 'kb_search_all',  | 0.0s |
| S70 | S70-08 | Memory MCP round-trip | ✅ PASS | stored+recalled: id=7af13be4, sim=0.42, 1 hits | 1.1s |