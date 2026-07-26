# Portal 5 Acceptance Test Results — V6

**Date:** 2026-07-26 11:02:26
**Git SHA:** 7b0dbd6c
**Sections:** S1, S3a, S10, S10c
**Runtime:** 6540s (109m 0s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 489 |
| ⚠️  WARN | 62 |
| ℹ️  INFO | 4 |
| **Total** | **555** |

**Code defects: 0 · Env issues: 0 · Unclassified: 62**

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.6 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.1s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: d17a5012 | 0.0s |
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 1.7s |
| S2 | S2-02 | Pipeline /health | ✅ PASS | backends=6/6, workspaces=88 | 0.0s |
| S2 | S2-03 | Ollama | ✅ PASS | 168 models | 0.1s |
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
| S2 | S2-15 | MCP security (:8919) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-17 | MLX Speech | ✅ PASS | HTTP 200 | 0.0s |
| S12 | S12-01 | SearXNG search | ✅ PASS | 32 results | 1.6s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.6s |
| S15 | S15-01 | Workspace root exists | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-02 | Workspace subdirectories | ✅ PASS | all present | 0.0s |
| S15 | S15-03 | OWUI uploads bind mount | ✅ PASS | host↔OWUI bidirectional | 0.2s |
| S15 | S15-04 | workspace helper imports | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-05 | AUDIO_STT_ENGINE disabled | ✅ PASS | empty (correct) | 0.1s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 169 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 2/4 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |
| S50 | S50-01 | Empty prompt handled gracefully | ✅ PASS | HTTP 200 | 5.9s |
| S50 | S50-02 | Oversized prompt handled | ✅ PASS | HTTP 200 | 12.2s |
| S50 | S50-03 | Invalid model slug handled | ✅ PASS | HTTP 200 \ | 0.0s |
| S50 | S50-04 | Pipeline /health surfaces backend count | ✅ PASS | healthy: 6 | 0.0s |
| S50 | S50-05 | Malformed JSON rejected | ✅ PASS | HTTP 400 | 0.0s |
| S50 | S50-06 | Missing auth rejected with 401 | ✅ PASS | HTTP 401 | 0.0s |
| S6 | S6-01 | auto-security routing | ✅ PASS | signals: ['sql', 'inject', 'sanitize'] \ | 0.0s |
| S6 | S6-02 | auto-redteam routing | ⚠️  WARN | signals: ['recon', 'exploit', 'pentest'] \ | 0.0s |
| S6 | S6-03 | auto-blueteam routing | ⚠️  WARN | signals: ['contain', 'backup', 'incident'] \ | 0.0s |
| S6 | S6-04 | Content-aware security routing | ⚠️  WARN | routed to security workspace: False  [UNCLASSIFIED] | 7.1s |
| S6 | S6-05 | auto-redteam-deep routing | ⚠️  WARN | signals: ['kerberoast', 'spn'] \ | 0.0s |
| S6 | S6-06 | auto-pentest routing (JANG-CRACK) | ⚠️  WARN | signals: ['impacket', 'getuserspns', 'kerberoast'] \ | 0.0s |
| S6 | S6-07 | auto-purpleteam-exec: routing + execute_ | ⚠️  WARN | signals: ['nmap', 'scan', 'open'] \ | 0.0s |
| S16 | S16-01 | Security MCP health | ✅ PASS | service: security-mcp | 0.0s |
| S21 | S21-01 | LLM router enabled | ✅ PASS | LLM_ROUTER_ENABLED=True | 0.0s |
| S21 | S21-02 | LLM router model available | ✅ PASS | model: hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterat | 0.0s |
| S21 | S21-03 | LLM router security intent | ⚠️  WARN | routed→auto-security::redteam \ | 0.0s |
| S21 | S21-04 | LLM router coding intent | ✅ PASS | routed→auto-coding \ | 0.0s |
| S21 | S21-05 | LLM router compliance intent | ✅ PASS | routed→auto-compliance \ | 0.0s |
| S21 | S21-06 | routing_descriptions.json | ✅ PASS | 18 workspace descriptions | 0.0s |
| S21 | S21-07 | routing_examples.json | ✅ PASS | 44 examples | 0.0s |
| S23 | S23-01 | GPT-OSS:20B available | ✅ PASS | gpt-oss in Ollama catalog: True | 0.0s |
| S23 | S23-03 | Gemma 4 E4B VLM available | ✅ PASS | gemma4:e4b in Ollama catalog: True | 0.0s |
| S23 | S23-04 | Phi-4 available | ✅ PASS | phi4:14b in Ollama catalog: True | 0.0s |
| S23 | S23-05 | Magistral-Small available | ✅ PASS | magistral in Ollama catalog: True | 0.0s |
| S23 | S23-06 | Phi-4-reasoning-plus available | ✅ PASS | phi4-reasoning in Ollama catalog: True | 0.0s |
| S23 | S23-07 | GLM-4.7-Flash available | ✅ PASS | glm-4.7-flash in Ollama catalog: True | 0.0s |
| S4 | S4-01 | Documents MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S4 | S4-05 | MCP read_word_document | ✅ PASS | got 110 chars from sample.docx | 0.0s |
| S4 | S4-06 | MCP read_excel | ✅ PASS | got 110 chars from sample.xlsx | 0.0s |
| S4 | S4-07 | MCP read_powerpoint | ✅ PASS | got 110 chars from sample.pptx | 0.0s |
| S4 | S4-08 | MCP read_pdf | ✅ PASS | got 109 chars from sample.pdf | 0.0s |
| S5 | S5-01 | Sandbox MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S17 | S17-01 | CAD render MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S17 | S17-02 | Tools manifest — render_mesh / render_op | ✅ PASS | found: ['convert_cad', 'render_mesh', 'render_openscad'] | 0.0s |
| S17 | S17-04 | render_mesh PNG URL reachable via HTTP | ✅ PASS | GET http://localhost:8926/files/models3d/render_582d2290.png → 200 | 0.0s |
| S17 | S17-10 | auto-cad workspace — pipeline accepts re | ✅ PASS | HTTP 200 | 5.4s |
| S18 | S18-01 | Sandbox health + lab-exec posture | ✅ PASS | HTTP 200 \ | 0.0s |
| S8 | S8-01 | MLX Speech health | ✅ PASS | voice_cloning: True | 0.0s |
| S8 | S8-02 | MLX Speech TTS | ✅ PASS | duration: 2.85s | 3.8s |
| S9 | S9-01 | MLX Speech ASR available | ✅ PASS | Qwen3-ASR | 0.0s |
| S9 | S9-03 | MLX Transcribe health | ✅ PASS | HTTP 200 | 0.0s |
| S9 | S9-04 | MLX Transcribe diarization | ⚠️  WARN | only 1 speaker(s) detected  [UNCLASSIFIED] | 19.2s |
| S9 | S9-05 | Workspace upload resolution | ⚠️  WARN | HTTP 404  [UNCLASSIFIED] | 0.0s |
| S7 | S7-01 | Music MCP health | ✅ PASS | service: music-mcp | 0.0s |
| S30 | S30-01 | ComfyUI direct | ✅ PASS | version: 0.27.0 | 0.0s |
| S30 | S30-02 | ComfyUI MCP bridge | ✅ PASS | HTTP 200 | 0.0s |
| S31 | S31-01 | Video MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S41 | S41-01 | /health/all aggregator | ✅ PASS | 14/19 services ok: pipeline, ollama, mcp_comfyui, mcp_video, mcp_music | 0.1s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-e2b-pentest limit=5, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-1p2b limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-230m limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-02 | bench-* concurrency=1 | ⚠️  WARN | bench-lfm-micro-350m limit=2, expected 1  [UNCLASSIFIED] | 0.0s |
| S41 | S41-03 | /admin/refresh-tools | ✅ PASS | 61 tools registered | 0.0s |
| S41 | S41-04 | Power metrics in /metrics | ✅ PASS | portal5_power_* and portal5_energy_* present | 0.0s |
| S41 | S41-05 | Workspace consistency | ✅ PASS | 88 workspaces, pipe+yaml match | 0.0s |
| S42 | S42-01 | Browser MCP health | ✅ PASS | status=ok, profiles=0 | 0.0s |
| S42 | S42-02 | Browser MCP tools | ✅ PASS | 8 tools: browser_navigate, browser_snapshot, browser_click, browser_fill... | 0.0s |
| S60 | S60-01 | Tool registry loaded | ✅ PASS | 0 tools: ... | 0.0s |
| S60 | S60-02 | Workspace tool whitelists | ✅ PASS | 31/88 workspaces have tools | 0.0s |
| S60 | S60-03 | Persona tool resolution | ✅ PASS | tools_allow override works: ['execute_python'] | 0.0s |
| S60 | S60-04 | Tool dispatch function | ✅ PASS | exists | 0.0s |
| S60 | S60-05 | MAX_TOOL_HOPS | ✅ PASS | value=20 | 0.0s |
| S60 | S60-06 | Tool-call Prometheus metrics | ✅ PASS | portal5_tool_calls_total + duration present | 0.0s |
| S60 | S60-07 | agentorchestrator persona | ✅ PASS | slug=agentorchestrator, workspace=auto-coding | 0.0s |
| S70 | S70-01 | SearXNG web search | ✅ PASS | 1 results returned | 0.3s |
| S70 | S70-02 | Research MCP health | ✅ PASS | {"status":"ok","service":"research-mcp","backend":"searxng"} | 0.0s |
| S70 | S70-03 | Memory MCP health | ✅ PASS | {"status":"ok","service":"memory-mcp","stored":23} | 0.0s |
| S70 | S70-04 | RAG MCP health | ✅ PASS | {"status":"ok","service":"rag-mcp","knowledge_bases":[]} | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ✅ PASS | tools: ['web_search', 'web_fetch', 'news_search', 'kb_search', 'kb_search_all', | 0.0s |
| S70 | S70-08 | Memory MCP round-trip | ✅ PASS | stored+recalled: id=ad3bd9a0, sim=0.43, 1 hits | 0.4s |
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 6 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 88 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 138 personas | 0.1s |
| S1 | S1-05 | Persona count matches yaml file count | ✅ PASS | 138 loaded, 138 yaml files | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 21 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-09 | MLX routing: text-only models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ✅ PASS | all 138 personas use valid workspace_model values | 0.0s |
| S1 | S1-11 | All personas have PERSONA_PROMPTS entrie | ✅ PASS | all 104 non-benchmark personas covered | 0.0s |
| S1 | S1-17 | workspace hint reachability | ✅ PASS | all 88 workspace hints resolve | 0.1s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> auto matches Ollama:qwen3.5-ablite | 8.9s |
| S3a | S3a-02 | Workspace auto-daily | ✅ PASS | signals: ['offsite', 'venue', 'agenda'] \| routed -> auto-daily matches Ollama:g | 10.8s |
| S3a | S3a-03 | Workspace auto-coding+model=magistral | ⚠️  WARN | signals OK but ROUTING MISMATCH: got auto-coding::model=hf.co/unsloth/Magistr, e | 53.9s |
| S3a | S3a-04 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum', 'sample'] \| routed -> auto-music matches Ollama:lfm2. | 6.4s |
| S3a | S3a-05 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> auto-video matches Ollama:gra | 13.4s |
| S3a | S3a-06 | Workspace auto-coding | ✅ PASS | signals: ['def', 'return', 'reverse'] \| routed -> auto-coding matches Ollama:qw | 25.0s |
| S3a | S3a-07 | Workspace auto-coding+laguna | ⚠️  WARN | signals OK but ROUTING MISMATCH: got auto-coding::laguna, expected Ollama:qwen3- | 137.7s |
| S3a | S3a-08 | Workspace auto-coding+heavy | ⚠️  WARN | signals OK but ROUTING MISMATCH: got auto-coding::heavy, expected Ollama:qwen3-c | 39.3s |
| S3a | S3a-09 | Workspace auto-spl | ✅ PASS | signals: ['fail', 'login'] \| routed -> auto-spl matches Ollama:huihui-ai_qwen3- | 24.0s |
| S3a | S3a-10 | Workspace auto-documents | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches Ollama:granite4.1  [UNCLASSI | 14.2s |
| S3a | S3a-11 | Workspace auto-security | ✅ PASS | signals: ['authentication', 'OWASP'] \| routed -> auto-security matches Ollama:v | 12.0s |
| S3a | S3a-12 | Workspace auto-security+redteam | ⚠️  WARN | signals OK but ROUTING MISMATCH: got auto-security::redteam, expected Ollama:vul | 13.5s |
| S3a | S3a-13 | Workspace auto-security+blueteam | ⚠️  WARN | signals OK but ROUTING MISMATCH: got auto-security::blueteam, expected Ollama:vu | 16.7s |
| S3a | S3a-14 | Workspace auto-reasoning | ✅ PASS | signals: ['mile', 'distance', '60'] \| routed -> auto-reasoning matches Ollama:d | 12.3s |
| S3a | S3a-15 | Workspace auto-council | ✅ PASS | signals: ['Code-determined decision', 'Participation', 'votes'] \| routed -> aut | 368.1s |
| S3a | S3a-16 | Workspace auto-research | ✅ PASS | signals: ['qubit', 'quantum', 'compute'] \| routed -> auto-research matches Olla | 35.6s |
| S3a | S3a-17 | Workspace auto-data | ✅ PASS | signals: ['mean', 'deviation', 'σ'] \| routed -> auto-data matches Ollama:granit | 46.8s |
| S3a | S3a-18 | Workspace auto-compliance | ✅ PASS | signals: ['CIP', 'evidence', 'patch'] \| routed -> auto-compliance matches Ollam | 21.4s |
| S3a | S3a-19 | Workspace auto-math | ✅ PASS | signals: ['integral', 'intersection', 'area'] \| routed -> auto-math matches Oll | 8.0s |
| S3a | S3a-20 | Workspace auto-creative | ✅ PASS | signals: ['haiku', 'syllable', '5-7-5'] \| routed -> auto-creative matches Ollam | 21.9s |
| S3a | S3a-21 | Workspace auto-vision | ✅ PASS | signals: ['alt', 'text', 'contrast'] \| routed -> auto-reasoning matches Ollama: | 12.4s |
| S3a | S3a-22 | Workspace auto-audio | ✅ PASS | signals: ['audio', 'transcri', 'format'] \| routed -> auto-audio matches Ollama: | 18.7s |
| S3a | S3a-23 | Workspace tools-specialist | ✅ PASS | signals: ['tool', 'function', 'JSON'] \| routed -> tools-specialist matches Olla | 4.2s |
| S10 | S10-01 | Persona itexpert | ✅ PASS | signals: ['troubleshoot'] \| routed -> auto matches via workspace 'auto': Ollama | 12.5s |
| S10 | S10-02 | Persona techreviewer | ✅ PASS | signals: ['feature', 'review'] \| routed -> auto matches via workspace 'auto': O | 7.9s |
| S10 | S10-03 | Persona webnavigator | ✅ PASS | signals: ['source', 'url'] \| routed -> auto matches via workspace 'auto': Ollam | 8.0s |
| S10 | S10-04 | Persona cadquerydesigner | ✅ PASS | signals: ['cadquery', 'cq', 'box'] \| routed -> auto-cad matches via workspace ' | 28.4s |
| S10 | S10-05 | Persona printabilityengineer | ✅ PASS | signals: ['overhang', 'support', '45'] \| routed -> auto-cad matches via workspa | 15.9s |
| S10 | S10-06 | Persona agenticheavy | ✅ PASS | signals: ['plan', 'stage', 'test'] \| routed -> auto-coding matches via workspac | 20.6s |
| S10 | S10-07 | Persona agenticlite | ✅ PASS | signals: ['test', 'fix'] \| routed -> auto-coding matches via workspace 'auto-co | 82.4s |
| S10 | S10-08 | Persona agentorchestrator | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-coding matches via workspac | 36.5s |
| S10 | S10-09 | Persona bugdiscoverycodeassistant | ✅ PASS | signals: ['indexerror', 'out of range', 'empty list'] \| routed -> auto-coding m | 6.5s |
| S10 | S10-10 | Persona codebasewikidocumentationskill | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.5s |
| S10 | S10-11 | Persona codereviewassistant | ✅ PASS | signals: ['list', 'comprehension', 'memory'] \| routed -> auto-coding matches vi | 5.7s |
| S10 | S10-12 | Persona codereviewer | ✅ PASS | signals: ['==', 'bool', 'True'] \| routed -> auto-coding matches via workspace ' | 6.5s |
| S10 | S10-13 | Persona codingagentic | ✅ PASS | signals: ['read', 'edit', 'test'] \| routed -> auto-coding matches via workspace | 37.1s |
| S10 | S10-14 | Persona codinguncensored | ✅ PASS | signals: ['length', 'buffer', 'size'] \| routed -> auto-coding matches via works | 11.7s |
| S10 | S10-15 | Persona codinguncensoredagentic | ✅ PASS | signals: ['debug', 'memory', 'verify'] \| routed -> auto-coding matches via work | 21.1s |
| S10 | S10-16 | Persona creativecoder | ✅ PASS | signals: ['canvas', 'ball', 'click'] \| routed -> auto-coding matches via worksp | 6.4s |
| S10 | S10-17 | Persona devopsautomator | ✅ PASS | signals: ['#!/', 'bash', 'date'] \| routed -> auto-coding matches via workspace  | 16.0s |
| S10 | S10-18 | Persona devstral_coder | ✅ PASS | signals: ['def', 'flatten', 'isinstance'] \| routed -> auto-coding matches via w | 6.6s |
| S10 | S10-19 | Persona e2edebugger | ✅ PASS | signals: ['plan', 'stage'] \| routed -> auto-coding matches via workspace 'auto- | 11.8s |
| S10 | S10-20 | Persona e2etestauthor | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-coding matches via workspac | 21.9s |
| S10 | S10-21 | Persona ethereumdeveloper | ✅ PASS | signals: ['contract', 'pragma', 'solidity'] \| routed -> auto-coding matches via | 7.3s |
| S10 | S10-22 | Persona excelsheet | ✅ PASS | signals: ['VLOOKUP', 'formula', 'range'] \| routed -> auto-coding matches via wo | 6.5s |
| S10 | S10-23 | Persona formfiller | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.5s |
| S10 | S10-24 | Persona fullstacksoftwaredeveloper | ✅ PASS | signals: ['REST', 'API'] \| routed -> auto-coding matches via workspace 'auto-co | 8.0s |
| S10 | S10-25 | Persona githubexpert | ✅ PASS | signals: ['rebase', 'merge', 'history'] \| routed -> auto-coding matches via wor | 6.5s |
| S10 | S10-26 | Persona glm-coder | ✅ PASS | signals: ['def', 'palindrome', 'reverse'] \| routed -> auto-coding matches via w | 6.2s |
| S10 | S10-27 | Persona goengineer | ✅ PASS | signals: ['middleware', 'http.handler', 'context'] \| routed -> auto-coding matc | 6.5s |
| S10 | S10-28 | Persona javascriptconsole | ✅ PASS | signals: ['18.84'] \| routed -> auto-coding matches via workspace 'auto-coding': | 3.8s |
| S10 | S10-29 | Persona kubernetesdockerrpglearningengin | ✅ PASS | signals: ['layer', 'image', 'cache'] \| routed -> auto-coding matches via worksp | 6.4s |
| S10 | S10-30 | Persona linuxterminal | ✅ PASS | signals: ['total', 'user', '-rw'] \| routed -> auto-coding matches via workspace | 6.5s |
| S10 | S10-31 | Persona pythoncodegeneratorcleanoptimize | ✅ PASS | signals: ['sorted', 'lambda', 'key'] \| routed -> auto-coding matches via worksp | 6.5s |
| S10 | S10-32 | Persona pythoninterpreter | ✅ PASS | signals: ['[3, 2, 1]', '3, 2, 1'] \| routed -> auto-coding matches via workspace | 2.4s |
| S10 | S10-33 | Persona rustengineer | ✅ PASS | signals: ['arc', 'mutex', 'rwlock'] \| routed -> auto-coding matches via workspa | 9.3s |
| S10 | S10-34 | Persona seniorfrontenddeveloper | ✅ PASS | signals: ['useState', 'useEffect', 'hook'] \| routed -> auto-coding matches via  | 12.3s |
| S10 | S10-35 | Persona softwarequalityassurancetester | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.5s |
| S10 | S10-36 | Persona sqlterminal | ✅ PASS | signals: ['SELECT', 'FROM', 'WHERE'] \| routed -> auto-coding matches via worksp | 2.7s |
| S10 | S10-37 | Persona terraformwriter | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 8.0s |
| S10 | S10-38 | Persona typescriptengineer | ⚠️  WARN | no signals in:  \| routed -> auto-coding matches via workspace 'auto-coding': Ol | 6.5s |
| S10 | S10-39 | Persona ux-uideveloper | ✅ PASS | signals: ['mobile'] \| routed -> auto-coding matches via workspace 'auto-coding' | 2.4s |
| S10 | S10-40 | Persona creativewriter | ✅ PASS | signals: ['rain', 'detective', 'dark'] \| routed -> auto-creative matches via wo | 26.2s |
| S10 | S10-41 | Persona hermes3writer | ✅ PASS | signals: ['detective', 'coastal', 'town'] \| routed -> auto-creative matches via | 5.3s |
| S10 | S10-42 | Persona interviewcoach | ✅ PASS | signals: ['situation', 'task', 'behavioral'] \| routed -> auto-creative matches  | 5.3s |
| S10 | S10-43 | Persona proofreader | ✅ PASS | signals: ['address', 'comma'] \| routed -> auto-creative matches via workspace ' | 5.3s |
| S10 | S10-44 | Persona dailydriver | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-45 | Persona gemma_e4b | ✅ PASS | signals: ['https', 'ssl', 'tls'] \| routed -> auto-daily matches via workspace ' | 21.5s |
| S10 | S10-46 | Persona gemma_fast | ✅ PASS | signals: ['rest', 'http', 'request'] \| routed -> auto-daily matches via workspa | 7.4s |
| S10 | S10-47 | Persona personalassistant | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> auto-daily matches via workspace | 7.4s |
| S10 | S10-48 | Persona dashboardarchitect | ⚠️  WARN | no signals in:  \| routed -> auto-data matches via workspace 'auto-data': Ollama | 66.8s |
| S10 | S10-49 | Persona dataanalyst | ✅ PASS | signals: ['correlation', 'causation', 'variable'] \| routed -> auto-data matches | 31.0s |
| S10 | S10-50 | Persona databasearchitect | ⚠️  WARN | no signals in:  \| routed -> auto-data matches via workspace 'auto-data': Ollama | 31.7s |
| S10 | S10-51 | Persona dataextractor | ⚠️  WARN | no signals in: ```json
{
  "name": "John Doe",
  "email": "john@example.com \| r | 14.8s |
| S10 | S10-52 | Persona datascientist | ✅ PASS | signals: ['feature', 'transform', 'engineer'] \| routed -> auto-data matches via | 30.7s |
| S10 | S10-53 | Persona machinelearningengineer | ✅ PASS | signals: ['gradient', 'descent', 'learning'] \| routed -> auto-data matches via  | 30.5s |
| S10 | S10-54 | Persona statistician | ✅ PASS | signals: ['null', 'hypothesis'] \| routed -> auto-data matches via workspace 'au | 31.1s |
| S10 | S10-55 | Persona documentationarchitect | ⚠️  WARN | no signals in:  \| routed -> auto-documents matches via workspace 'auto-document | 13.9s |
| S10 | S10-56 | Persona phi4specialist | ✅ PASS | signals: ['spec', 'requirement', 'section'] \| routed -> auto-documents matches  | 9.7s |
| S10 | S10-57 | Persona techwriter | ✅ PASS | signals: ['endpoint', 'request', 'response'] \| routed -> auto-documents matches | 10.0s |
| S10 | S10-58 | Persona transcriptanalyst | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-59 | Persona mathreasoner | ✅ PASS | signals: ['eigenvalue', 'characteristic polynomial', 'det'] \| routed -> auto-ma | 8.9s |
| S10 | S10-60 | Persona businessanalyst | ✅ PASS | signals: ['stakeholder', 'functional'] \| routed -> auto-reasoning matches via w | 10.3s |
| S10 | S10-61 | Persona devopsengineer | ✅ PASS | signals: ['pod', 'pending', 'running'] \| routed -> auto-reasoning matches via w | 6.5s |
| S10 | S10-62 | Persona glm-thinker | ✅ PASS | signals: ['halting', 'turing', 'undecidable'] \| routed -> auto-reasoning matche | 6.2s |
| S10 | S10-63 | Persona gptossanalyst | ✅ PASS | signals: ['trade', 'complex', 'maintain'] \| routed -> auto-reasoning matches vi | 6.5s |
| S10 | S10-64 | Persona itarchitect | ✅ PASS | signals: ['availability'] \| routed -> auto-reasoning matches via workspace 'aut | 6.3s |
| S10 | S10-65 | Persona magistralstrategist | ✅ PASS | signals: ['milestone', 'KPI', 'launch'] \| routed -> auto-reasoning matches via  | 6.4s |
| S10 | S10-66 | Persona phi4stemanalyst | ✅ PASS | signals: ['pythagor', 'triangle', 'hypotenuse'] \| routed -> auto-reasoning matc | 6.3s |
| S10 | S10-67 | Persona productmanager | ✅ PASS | signals: ['success metric', 'rice'] \| routed -> auto-reasoning matches via work | 6.4s |
| S10 | S10-68 | Persona seniorsoftwareengineersoftwarear | ✅ PASS | signals: ['pattern', 'load', 'scale'] \| routed -> auto-reasoning matches via wo | 6.3s |
| S10 | S10-69 | Persona factchecker | ✅ PASS | signals: ['source'] \| routed -> auto-research matches via workspace 'auto-resea | 22.0s |
| S10 | S10-70 | Persona gemmaresearchanalyst | ✅ PASS | signals: ['method', 'data', 'collect'] \| routed -> auto-research matches via wo | 4.0s |
| S10 | S10-71 | Persona kbnavigator | ✅ PASS | signals: ['search', 'query', 'results'] \| routed -> auto-research matches via w | 6.1s |
| S10 | S10-72 | Persona marketanalyst | ✅ PASS | signals: ['trend', 'growth', 'quarter'] \| routed -> auto-research matches via w | 6.1s |
| S10 | S10-73 | Persona paywalledresearcher | ✅ PASS | signals: ['source'] \| routed -> auto-research matches via workspace 'auto-resea | 6.0s |
| S10 | S10-74 | Persona researchanalyst | ✅ PASS | signals: ['systematic', 'search', 'literature'] \| routed -> auto-research match | 5.0s |
| S10 | S10-75 | Persona supergemma4researcher | ✅ PASS | signals: ['OSINT', 'search', 'verify'] \| routed -> auto-research matches via wo | 26.7s |
| S10 | S10-76 | Persona webresearcher | ✅ PASS | signals: ['source'] \| routed -> auto-research matches via workspace 'auto-resea | 4.7s |
| S10 | S10-77 | Persona adversarysimulator | ✅ PASS | signals: ['lateral', 'movement', 'T1'] \| routed -> auto-security matches via wo | 15.8s |
| S10 | S10-78 | Persona blueteamdefender | ✅ PASS | signals: ['extension', 'ransom', 'detect'] \| routed -> auto-security matches vi | 7.5s |
| S10 | S10-79 | Persona cybersecurityspecialist | ✅ PASS | signals: ['zero', 'trust'] \| routed -> auto-security matches via workspace 'aut | 7.7s |
| S10 | S10-80 | Persona networkengineer | ✅ PASS | signals: ['vlan', 'switchport', 'interface'] \| routed -> auto-security matches  | 7.7s |
| S10 | S10-81 | Persona pentester | ✅ PASS | signals: ['OWASP', 'test', 'methodology'] \| routed -> auto-security matches via | 8.0s |
| S10 | S10-82 | Persona pentestlead | ✅ PASS | signals: ['scanning', 'exploitation', 'tool'] \| routed -> auto-security matches | 8.3s |
| S10 | S10-83 | Persona purpleteamexec | ✅ PASS | signals: ['attack', 'credential', 'step'] \| routed -> auto-security matches via | 7.9s |
| S10 | S10-84 | Persona purpleteamlead | ✅ PASS | signals: ['attack', 'MITRE', 'detect'] \| routed -> auto-security matches via wo | 7.9s |
| S10 | S10-85 | Persona redteamoperator | ✅ PASS | signals: ['exploit', 'technique', 'initial'] \| routed -> auto-security matches  | 7.8s |
| S10 | S10-86 | Persona securityuncensored | ✅ PASS | signals: ['buffer', 'overflow', 'stack'] \| routed -> auto-security matches via  | 14.7s |
| S10 | S10-87 | Persona splunkdetectionauthor | ✅ PASS | signals: ['authentication', 't1110', 'mitre'] \| routed -> auto-spl matches via  | 33.4s |
| S10 | S10-88 | Persona splunksplgineer | ✅ PASS | signals: ['index', 'stats', 'count'] \| routed -> auto-spl matches via workspace | 8.7s |
| S10 | S10-89 | Persona chartanalyst | ✅ PASS | signals: ['quarter', 'revenue'] \| routed -> auto-reasoning matches via workspac | 10.7s |
| S10 | S10-90 | Persona codescreenshotreader | ✅ PASS | signals: ['function', 'code'] \| routed -> auto-reasoning matches via workspace  | 6.6s |
| S10 | S10-91 | Persona diagramreader | ✅ PASS | signals: ['components', 'abstraction'] \| routed -> auto-reasoning matches via w | 6.3s |
| S10 | S10-92 | Persona gemma4e4bvision | ✅ PASS | signals: ['stack', 'trace', 'error'] \| routed -> auto-reasoning matches via wor | 6.4s |
| S10 | S10-93 | Persona gemma4jangvision | ✅ PASS | signals: ['credential', 'password', 'screenshot'] \| routed -> auto-reasoning ma | 6.4s |
| S10 | S10-94 | Persona gemma_vision | ✅ PASS | signals: ['axis', 'label', 'value'] \| routed -> auto-reasoning matches via work | 6.4s |
| S10 | S10-95 | Persona ocrspecialist | ✅ PASS | signals: ['receipt', 'layout', 'total'] \| routed -> auto-reasoning matches via  | 6.4s |
| S10 | S10-96 | Persona whiteboardconverter | ✅ PASS | signals: ['relationships'] \| routed -> auto-reasoning matches via workspace 'au | 6.6s |
| S10 | S10-97 | Persona toolcomposer | ✅ PASS | signals: ['execute_python', 'remember', 'read'] \| routed -> tools-specialist ma | 17.0s |
| S10c | S10c-00 | fixture loaded | ✅ PASS | 317 concrete scenarios across compliance personas | 0.0s |
| S10c | S10c-001 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 14.3s |
| S10c | S10c-002 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 33.0s |
| S10c | S10c-003 | cippolicywriter/gap-analysis-table-struc | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 16.7s |
| S10c | S10c-004 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 40.0s |
| S10c | S10c-005 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 39.7s |
| S10c | S10c-006 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns \| model=auto-compliance  [UNC | 41.0s |
| S10c | S10c-007 | cippolicywriter/gap-analysis-table-struc | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 39.2s |
| S10c | S10c-008 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 2.9s |
| S10c | S10c-009 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 4.0s |
| S10c | S10c-010 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-011 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.7s |
| S10c | S10c-012 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-013 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-014 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 4.9s |
| S10c | S10c-015 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.4s |
| S10c | S10c-016 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.9s |
| S10c | S10c-017 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-018 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.5s |
| S10c | S10c-019 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.3s |
| S10c | S10c-020 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.3s |
| S10c | S10c-021 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.3s |
| S10c | S10c-022 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.1s |
| S10c | S10c-023 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-024 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.1s |
| S10c | S10c-025 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-026 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-027 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.8s |
| S10c | S10c-028 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.0s |
| S10c | S10c-029 | cippolicywriter/insufficient-context-vag | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-030 | cippolicywriter/policy-modal-verbs[NERC_ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.6s |
| S10c | S10c-031 | cippolicywriter/policy-modal-verbs[HIPAA | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-032 | cippolicywriter/policy-modal-verbs[GDPR] | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 15.0s |
| S10c | S10c-033 | cippolicywriter/policy-modal-verbs[SOC2] | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 13.2s |
| S10c | S10c-034 | cippolicywriter/policy-modal-verbs[PCI_D | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.8s |
| S10c | S10c-035 | cippolicywriter/policy-modal-verbs[NIST_ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 11.4s |
| S10c | S10c-036 | cippolicywriter/policy-modal-verbs[ISO_2 | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.1s |
| S10c | S10c-037 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.4s |
| S10c | S10c-038 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-039 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.2s |
| S10c | S10c-040 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-041 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 16.5s |
| S10c | S10c-042 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.0s |
| S10c | S10c-043 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-044 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 35.3s |
| S10c | S10c-045 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.1s |
| S10c | S10c-046 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.7s |
| S10c | S10c-047 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 18.6s |
| S10c | S10c-048 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 20.0s |
| S10c | S10c-049 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.5s |
| S10c | S10c-050 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.9s |
| S10c | S10c-051 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 51.7s |
| S10c | S10c-052 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 35.1s |
| S10c | S10c-053 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 34.6s |
| S10c | S10c-054 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 41.2s |
| S10c | S10c-055 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 42.3s |
| S10c | S10c-056 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 63.6s |
| S10c | S10c-057 | complianceanalyst/gap-analysis-table-str | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 56.0s |
| S10c | S10c-058 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.0s |
| S10c | S10c-059 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-060 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.2s |
| S10c | S10c-061 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.7s |
| S10c | S10c-062 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.8s |
| S10c | S10c-063 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-064 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.6s |
| S10c | S10c-065 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 11.5s |
| S10c | S10c-066 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.1s |
| S10c | S10c-067 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.4s |
| S10c | S10c-068 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 12.6s |
| S10c | S10c-069 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.8s |
| S10c | S10c-070 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-071 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.9s |
| S10c | S10c-072 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-073 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 12.0s |
| S10c | S10c-074 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.6s |
| S10c | S10c-075 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.6s |
| S10c | S10c-076 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.8s |
| S10c | S10c-077 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.3s |
| S10c | S10c-078 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.6s |
| S10c | S10c-079 | complianceanalyst/insufficient-context-v | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.7s |
| S10c | S10c-080 | complianceanalyst/policy-modal-verbs[NER | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 17.5s |
| S10c | S10c-081 | complianceanalyst/policy-modal-verbs[HIP | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.6s |
| S10c | S10c-082 | complianceanalyst/policy-modal-verbs[GDP | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 24.6s |
| S10c | S10c-083 | complianceanalyst/policy-modal-verbs[SOC | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.4s |
| S10c | S10c-084 | complianceanalyst/policy-modal-verbs[PCI | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.7s |
| S10c | S10c-085 | complianceanalyst/policy-modal-verbs[NIS | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 11.4s |
| S10c | S10c-086 | complianceanalyst/policy-modal-verbs[ISO | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 14.8s |
| S10c | S10c-087 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-088 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-089 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.4s |
| S10c | S10c-090 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.0s |
| S10c | S10c-091 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=auto-compliance  [UNC | 5.2s |
| S10c | S10c-092 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 16.3s |
| S10c | S10c-093 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.0s |
| S10c | S10c-094 | complianceanalyst/cross-framework-mappin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 14.2s |
| S10c | S10c-095 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 18.7s |
| S10c | S10c-096 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 15.5s |
| S10c | S10c-097 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 16.2s |
| S10c | S10c-098 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 21.7s |
| S10c | S10c-099 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.6s |
| S10c | S10c-100 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 17.3s |
| S10c | S10c-101 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.2s |
| S10c | S10c-102 | complianceanalyst/long-context-multi-cit | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53], anti_fabrication.refusal_ | 55.9s |
| S10c | S10c-103 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 60.3s |
| S10c | S10c-104 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 48.2s |
| S10c | S10c-105 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 57.1s |
| S10c | S10c-106 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 56.7s |
| S10c | S10c-107 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 45.9s |
| S10c | S10c-108 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 59.3s |
| S10c | S10c-109 | gdprdpoadvisor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 54.8s |
| S10c | S10c-110 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.8s |
| S10c | S10c-111 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.2s |
| S10c | S10c-112 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.1s |
| S10c | S10c-113 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.4s |
| S10c | S10c-114 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-115 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 4.5s |
| S10c | S10c-116 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.1s |
| S10c | S10c-117 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.0s |
| S10c | S10c-118 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.4s |
| S10c | S10c-119 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.2s |
| S10c | S10c-120 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.3s |
| S10c | S10c-121 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.2s |
| S10c | S10c-122 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.2s |
| S10c | S10c-123 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 12.8s |
| S10c | S10c-124 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.9s |
| S10c | S10c-125 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.1s |
| S10c | S10c-126 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.6s |
| S10c | S10c-127 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.5s |
| S10c | S10c-128 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.5s |
| S10c | S10c-129 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-130 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-131 | gdprdpoadvisor/insufficient-context-vagu | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.8s |
| S10c | S10c-132 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 3.8s |
| S10c | S10c-133 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-134 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-135 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-136 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-137 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 4.3s |
| S10c | S10c-138 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.9s |
| S10c | S10c-139 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 16.2s |
| S10c | S10c-140 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 22.2s |
| S10c | S10c-141 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.8s |
| S10c | S10c-142 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.0s |
| S10c | S10c-143 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.2s |
| S10c | S10c-144 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.0s |
| S10c | S10c-145 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.2s |
| S10c | S10c-146 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 59.6s |
| S10c | S10c-147 | hipaaprivacyofficer/gap-analysis-table-s | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 41.6s |
| S10c | S10c-148 | hipaaprivacyofficer/gap-analysis-table-s | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 33.9s |
| S10c | S10c-149 | hipaaprivacyofficer/gap-analysis-table-s | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 36.2s |
| S10c | S10c-150 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 62.3s |
| S10c | S10c-151 | hipaaprivacyofficer/gap-analysis-table-s | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 41.9s |
| S10c | S10c-152 | hipaaprivacyofficer/gap-analysis-table-s | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 52.7s |
| S10c | S10c-153 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.0s |
| S10c | S10c-154 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.2s |
| S10c | S10c-155 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.4s |
| S10c | S10c-156 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.0s |
| S10c | S10c-157 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.1s |
| S10c | S10c-158 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.3s |
| S10c | S10c-159 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.4s |
| S10c | S10c-160 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.1s |
| S10c | S10c-161 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.2s |
| S10c | S10c-162 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.0s |
| S10c | S10c-163 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-164 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.0s |
| S10c | S10c-165 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-166 | hipaaprivacyofficer/anti-fabrication-ver | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.8s |
| S10c | S10c-167 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.9s |
| S10c | S10c-168 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.6s |
| S10c | S10c-169 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.4s |
| S10c | S10c-170 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-171 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 11.9s |
| S10c | S10c-172 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.0s |
| S10c | S10c-173 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.2s |
| S10c | S10c-174 | hipaaprivacyofficer/insufficient-context | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-175 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.7s |
| S10c | S10c-176 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-177 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.4s |
| S10c | S10c-178 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.9s |
| S10c | S10c-179 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-180 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 5.9s |
| S10c | S10c-181 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.7s |
| S10c | S10c-182 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.8s |
| S10c | S10c-183 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 15.5s |
| S10c | S10c-184 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.3s |
| S10c | S10c-185 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 10.1s |
| S10c | S10c-186 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.6s |
| S10c | S10c-187 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 19.5s |
| S10c | S10c-188 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.5s |
| S10c | S10c-189 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 9.6s |
| S10c | S10c-190 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 24.7s |
| S10c | S10c-191 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 32.7s |
| S10c | S10c-192 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 32.1s |
| S10c | S10c-193 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 42.0s |
| S10c | S10c-194 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 43.6s |
| S10c | S10c-195 | nerccipcomplianceanalyst/gap-analysis-ta | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 61.0s |
| S10c | S10c-196 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-197 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.8s |
| S10c | S10c-198 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.4s |
| S10c | S10c-199 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-200 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-201 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-202 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 12.9s |
| S10c | S10c-203 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.4s |
| S10c | S10c-204 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-205 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.7s |
| S10c | S10c-206 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.4s |
| S10c | S10c-207 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 7.8s |
| S10c | S10c-208 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.7s |
| S10c | S10c-209 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 26.1s |
| S10c | S10c-210 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.0s |
| S10c | S10c-211 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.8s |
| S10c | S10c-212 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.3s |
| S10c | S10c-213 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.2s |
| S10c | S10c-214 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 15.5s |
| S10c | S10c-215 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.6s |
| S10c | S10c-216 | nerccipcomplianceanalyst/refuse-to-certi | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-217 | nerccipcomplianceanalyst/insufficient-co | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-218 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 15.8s |
| S10c | S10c-219 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.4s |
| S10c | S10c-220 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.6s |
| S10c | S10c-221 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.3s |
| S10c | S10c-222 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 22.9s |
| S10c | S10c-223 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-224 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-225 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 15.7s |
| S10c | S10c-226 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.9s |
| S10c | S10c-227 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 39.3s |
| S10c | S10c-228 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.1s |
| S10c | S10c-229 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.0s |
| S10c | S10c-230 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 18.2s |
| S10c | S10c-231 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 29.3s |
| S10c | S10c-232 | pcidssassessor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 33.6s |
| S10c | S10c-233 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 23.1s |
| S10c | S10c-234 | pcidssassessor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 31.2s |
| S10c | S10c-235 | pcidssassessor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 36.8s |
| S10c | S10c-236 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 50.5s |
| S10c | S10c-237 | pcidssassessor/gap-analysis-table-struct | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 63.0s |
| S10c | S10c-238 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns \| model=auto-compliance  [UNC | 57.4s |
| S10c | S10c-239 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.3s |
| S10c | S10c-240 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.2s |
| S10c | S10c-241 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-242 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.2s |
| S10c | S10c-243 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.9s |
| S10c | S10c-244 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-245 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-246 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.9s |
| S10c | S10c-247 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.0s |
| S10c | S10c-248 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-249 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-250 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-251 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.5s |
| S10c | S10c-252 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.1s |
| S10c | S10c-253 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.2s |
| S10c | S10c-254 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.5s |
| S10c | S10c-255 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.5s |
| S10c | S10c-256 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.1s |
| S10c | S10c-257 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.8s |
| S10c | S10c-258 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-259 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.0s |
| S10c | S10c-260 | pcidssassessor/insufficient-context-vagu | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.3s |
| S10c | S10c-261 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=auto-compliance  [UN | 4.7s |
| S10c | S10c-262 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-263 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-264 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.9s |
| S10c | S10c-265 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=auto-compliance  [UNC | 4.6s |
| S10c | S10c-266 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=auto-compliance   | 4.9s |
| S10c | S10c-267 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-268 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 21.3s |
| S10c | S10c-269 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.1s |
| S10c | S10c-270 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.1s |
| S10c | S10c-271 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 9.0s |
| S10c | S10c-272 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 8.5s |
| S10c | S10c-273 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 26.3s |
| S10c | S10c-274 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 12.0s |
| S10c | S10c-275 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 20.3s |
| S10c | S10c-276 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 23.2s |
| S10c | S10c-277 | soc2auditor/gap-analysis-table-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 46.2s |
| S10c | S10c-278 | soc2auditor/gap-analysis-table-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 36.8s |
| S10c | S10c-279 | soc2auditor/gap-analysis-table-structure | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 20.8s |
| S10c | S10c-280 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 41.9s |
| S10c | S10c-281 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 56.8s |
| S10c | S10c-282 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 3.6s |
| S10c | S10c-283 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.4s |
| S10c | S10c-284 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-285 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-286 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 2.4s |
| S10c | S10c-287 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=auto-compliance  [U | 3.6s |
| S10c | S10c-288 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 1.8s |
| S10c | S10c-289 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 9.5s |
| S10c | S10c-290 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 3.8s |
| S10c | S10c-291 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.0s |
| S10c | S10c-292 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-293 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-294 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.6s |
| S10c | S10c-295 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 16.9s |
| S10c | S10c-296 | soc2auditor/refuse-to-certify-binary[NER | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 6.3s |
| S10c | S10c-297 | soc2auditor/refuse-to-certify-binary[HIP | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.9s |
| S10c | S10c-298 | soc2auditor/refuse-to-certify-binary[GDP | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.2s |
| S10c | S10c-299 | soc2auditor/refuse-to-certify-binary[SOC | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 8.3s |
| S10c | S10c-300 | soc2auditor/refuse-to-certify-binary[PCI | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.1s |
| S10c | S10c-301 | soc2auditor/refuse-to-certify-binary[NIS | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 10.9s |
| S10c | S10c-302 | soc2auditor/refuse-to-certify-binary[ISO | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.1s |
| S10c | S10c-303 | soc2auditor/insufficient-context-vague-p | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-304 | soc2auditor/citation-format-discipline[N | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.9s |
| S10c | S10c-305 | soc2auditor/citation-format-discipline[H | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 5.3s |
| S10c | S10c-306 | soc2auditor/citation-format-discipline[G | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.7s |
| S10c | S10c-307 | soc2auditor/citation-format-discipline[S | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.5s |
| S10c | S10c-308 | soc2auditor/citation-format-discipline[P | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.8s |
| S10c | S10c-309 | soc2auditor/citation-format-discipline[N | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.6s |
| S10c | S10c-310 | soc2auditor/citation-format-discipline[I | ✅ PASS | all 1 assertions OK \| model=auto-compliance | 4.9s |
| S10c | S10c-311 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.8s |
| S10c | S10c-312 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 18.3s |
| S10c | S10c-313 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.6s |
| S10c | S10c-314 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 11.5s |
| S10c | S10c-315 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 13.7s |
| S10c | S10c-316 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 20.5s |
| S10c | S10c-317 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=auto-compliance | 14.8s |