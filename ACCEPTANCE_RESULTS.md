# Portal 5 Acceptance Test Results — V6

**Date:** 2026-06-12 10:03:00
**Git SHA:** f945eb6
**Sections:** S0, S1, S2, S3a, S4, S5, S6, S7, S8, S9, S10, S10c, S12, S13, S15, S16, S21, S23, S30, S31, S40, S41, S42, S50, S60, S70
**Notes:** Blended from 3 runs — full run (798614d), targeted rerun (5c64a01), standalone S10c with [:8000] fix (f945eb6)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 325 |
| ❌ FAIL | 58 |
| ⚠️  WARN | 215 |
| ℹ️  INFO | 10 |
| **Total** | **608** |

## Results

| Section | Test ID | Name | Status | Detail | Duration |
|---------|---------|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.5 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.2s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: fa16de3 | 0.0s |
| S1 | S1-01 | backends.yaml exists | ✅ PASS | /Users/chris/projects/portal-5/config/backends.yaml | 0.0s |
| S1 | S1-02 | backends.yaml valid YAML | ✅ PASS | 6 backends | 0.0s |
| S1 | S1-03 | Workspace IDs consistent | ✅ PASS | 73 workspaces | 0.0s |
| S1 | S1-04 | Persona YAMLs valid | ✅ PASS | 139 personas | 0.1s |
| S1 | S1-05 | Persona count matches yaml file count | ✅ PASS | 139 loaded, 139 yaml files | 0.0s |
| S1 | S1-06 | routing_descriptions.json | ✅ PASS | 19 descriptions | 0.0s |
| S1 | S1-07 | routing_examples.json | ✅ PASS | 3 examples | 0.0s |
| S1 | S1-08 | MLX routing: VLM models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-09 | MLX routing: text-only models (retired) | ℹ️  INFO | MLX proxy retired in 3a0c58e | 0.0s |
| S1 | S1-10 | Persona workspace_model values are pipel | ❌ FAIL | invalid: ['bench-qwen36-abl-27b:Qwen3.6-abliterated:27b']  [UNCLASSIFIED] | 0.0s |
| S1 | S1-11 | All personas have PERSONA_PROMPTS entrie | ✅ PASS | all 86 non-benchmark personas covered | 0.0s |
| S1 | S1-17 | workspace hint reachability | ✅ PASS | all 73 workspace hints resolve | 0.2s |
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 0.6s |
| S2 | S2-02 | Pipeline /health | ✅ PASS | backends=6/6, workspaces=74 | 0.0s |
| S2 | S2-03 | Ollama | ✅ PASS | 72 models | 0.0s |
| S2 | S2-04 | Open WebUI | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-05 | SearXNG | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-06 | Prometheus | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-07 | Grafana | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-08 | MCP documents (:8913) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-09 | MCP music (:8912) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-10 | MCP tts (:8916) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-11 | MCP whisper (:8915) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-12 | MCP sandbox (:8914) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-13 | MCP video (:8911) | ⚠️  WARN | HTTP 0  [UNCLASSIFIED] | 0.0s |
| S2 | S2-14 | MCP embedding (:8917) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-15 | MCP security (:8919) | ✅ PASS | HTTP 200 | 0.0s |
| S2 | S2-17 | MLX Speech | ✅ PASS | HTTP 200 | 0.0s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> huihui_ai/qwen3.5-abliterated:9b m | 13.1s |
| S3a | S3a-02 | Workspace auto-daily | ✅ PASS | signals: ['offsite', 'venue', 'agenda'] \| routed -> gemma4:26b-a4b-it-qat match | 18.6s |
| S3a | S3a-03 | Workspace auto-mistral | ✅ PASS | signals: ['trade', 'deploy'] \| routed -> hf.co/unsloth/Magistral-Small-2509-GGU | 46.6s |
| S3a | S3a-04 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum', 'sample'] \| routed -> lfm2.5:8b matches Ollama:lfm2.5 | 6.3s |
| S3a | S3a-05 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> granite4.1:8b matches Ollama: | 11.8s |
| S3a | S3a-06 | Workspace auto-coding | ✅ PASS | signals: ['def', 'return', 'reverse'] \| routed -> qwen3-coder:30b-a3b-q4_K_M ma | 14.8s |
| S3a | S3a-07 | Workspace auto-agentic | ✅ PASS | signals: ['service', 'API', 'domain'] \| routed -> qwen3-coder-next matches Olla | 41.4s |
| S3a | S3a-08 | Workspace auto-spl | ✅ PASS | signals: ['index', 'source', 'fail'] \| routed -> hf.co/bartowski/huihui-ai_Qwen | 33.2s |
| S3a | S3a-09 | Workspace auto-documents | ⚠️  WARN | no signals in:  \| routed -> granite4.1:8b matches Ollama:granite4.1  [UNCLASSIF | 13.9s |
| S3a | S3a-10 | Workspace auto-security | ✅ PASS | signals: ['OWASP'] \| routed -> baronllm:q6_k matches Ollama:baronllm | 12.5s |
| S3a | S3a-11 | Workspace auto-redteam | ⚠️  WARN | signals OK but ROUTING MISMATCH: got dolphin-llama3:8b, expected Ollama:baronllm | 7.1s |
| S3a | S3a-12 | Workspace auto-blueteam | ✅ PASS | signals: ['network', 'monitor', 'detect'] \| routed -> hf.co/fdtn-ai/Foundation- | 17.4s |
| S3a | S3a-13 | Workspace auto-reasoning | ✅ PASS | signals: ['150', 'mile', 'distance'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528 | 13.9s |
| S3a | S3a-14 | Workspace auto-research | ✅ PASS | signals: ['quantum'] \| routed -> huihui_ai/tongyi-deepresearch-abliterate match | 23.9s |
| S3a | S3a-15 | Workspace auto-data | ✅ PASS | signals: ['n-1', 'square root', 'mean'] \| routed -> deepseek-r1:32b-q8_0 matche | 66.2s |
| S3a | S3a-16 | Workspace auto-compliance | ✅ PASS | signals: ['CIP', 'evidence', 'compliance'] \| routed -> granite4.1:8b matches Ol | 20.8s |
| S3a | S3a-17 | Workspace auto-math | ✅ PASS | signals: ['integral', 'intersection', 'area'] \| routed -> phi4-mini-reasoning m | 7.8s |
| S3a | S3a-18 | Workspace auto-creative | ✅ PASS | signals: ['haiku', 'syllable', '5-7-5'] \| routed -> fredrezones55/Qwen3.6-35B-A | 20.4s |
| S3a | S3a-19 | Workspace auto-vision | ✅ PASS | signals: ['alt', 'text', 'contrast'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528 | 11.3s |
| S3a | S3a-20 | Workspace auto-audio | ✅ PASS | signals: ['audio', 'transcri', 'speech'] \| routed -> gemma4:12b-it-qat matches  | 17.5s |
| S3a | S3a-21 | Workspace tools-specialist | ✅ PASS | signals: ['tool', 'function', 'JSON'] \| routed -> granite4.1:8b matches Ollama: | 9.3s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| routed -> huihui_ai/qwen3.5-abliterated:9b m | 13.0s |
| S3a | S3a-02 | Workspace auto-daily | ✅ PASS | signals: ['offsite', 'agenda', 'plan'] \| routed -> gemma4:26b-a4b-it-qat matche | 18.6s |
| S3a | S3a-03 | Workspace auto-mistral | ✅ PASS | signals: ['trade', 'deploy'] \| routed -> hf.co/unsloth/Magistral-Small-2509-GGU | 43.1s |
| S3a | S3a-04 | Workspace auto-music | ✅ PASS | signals: ['beat'] \| routed -> lfm2.5:8b matches Ollama:lfm2.5 | 6.0s |
| S3a | S3a-05 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| routed -> granite4.1:8b matches Ollama: | 11.1s |
| S3a | S3a-06 | Workspace auto-coding | ✅ PASS | signals: ['def', 'return', 'reverse'] \| routed -> qwen3-coder:30b-a3b-q4_K_M ma | 19.6s |
| S3a | S3a-07 | Workspace auto-agentic | ✅ PASS | signals: ['service', 'API', 'domain'] \| routed -> qwen3-coder-next matches Olla | 39.9s |
| S3a | S3a-08 | Workspace auto-spl | ✅ PASS | signals: ['index', 'source', 'fail'] \| routed -> hf.co/bartowski/huihui-ai_Qwen | 29.8s |
| S3a | S3a-09 | Workspace auto-documents | ⚠️  WARN | no signals in:  \| routed -> granite4.1:8b matches Ollama:granite4.1  [UNCLASSIF | 13.7s |
| S3a | S3a-10 | Workspace auto-security | ⚠️  WARN | signals OK but ROUTING MISMATCH: got qwen3-vl:32b, expected Ollama:baronllm  [UN | 69.0s |
| S3a | S3a-11 | Workspace auto-redteam | ⚠️  WARN | signals OK but ROUTING MISMATCH: got qwen3-vl:32b, expected Ollama:baronllm  [UN | 65.9s |
| S3a | S3a-12 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| routed -> hf.co/fdtn-ai/Foundation | 17.9s |
| S3a | S3a-13 | Workspace auto-reasoning | ✅ PASS | signals: ['150', 'mile', 'distance'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528 | 11.1s |
| S3a | S3a-14 | Workspace auto-research | ✅ PASS | signals: ['quantum'] \| routed -> huihui_ai/tongyi-deepresearch-abliterate match | 21.9s |
| S3a | S3a-15 | Workspace auto-data | ✅ PASS | signals: ['mean', 'deviation'] \| routed -> deepseek-r1:32b-q8_0 matches Ollama: | 61.5s |
| S3a | S3a-16 | Workspace auto-compliance | ✅ PASS | signals: ['CIP', 'evidence', 'patch'] \| routed -> granite4.1:8b matches Ollama: | 16.9s |
| S3a | S3a-17 | Workspace auto-math | ✅ PASS | signals: ['intersection', 'area', '2x'] \| routed -> phi4-mini-reasoning matches | 7.8s |
| S3a | S3a-18 | Workspace auto-creative | ✅ PASS | signals: ['haiku', 'syllable', '5-7-5'] \| routed -> fredrezones55/Qwen3.6-35B-A | 21.2s |
| S3a | S3a-19 | Workspace auto-vision | ✅ PASS | signals: ['alt', 'text', 'contrast'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528 | 11.5s |
| S3a | S3a-20 | Workspace auto-audio | ✅ PASS | signals: ['audio', 'transcri', 'format'] \| routed -> gemma4:12b-it-qat matches  | 17.5s |
| S3a | S3a-21 | Workspace tools-specialist | ✅ PASS | signals: ['tool', 'function', 'JSON'] \| routed -> granite4.1:8b matches Ollama: | 4.9s |
| S4 | S4-01 | Documents MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S4 | S4-02 | Generate Word document | ✅ PASS | {
| S4 | S4-03 | Generate Excel spreadsheet | ✅ PASS | {
| S4 | S4-04 | Generate PowerPoint | ✅ PASS | {
| S4 | S4-05 | MCP read_word_document | ✅ PASS | got 110 chars from sample.docx | 0.0s |
| S4 | S4-06 | MCP read_excel | ✅ PASS | got 110 chars from sample.xlsx | 0.0s |
| S4 | S4-07 | MCP read_powerpoint | ✅ PASS | got 110 chars from sample.pptx | 0.0s |
| S4 | S4-08 | MCP read_pdf | ✅ PASS | got 109 chars from sample.pdf | 0.1s |
| S5 | S5-01 | Sandbox MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S5 | S5-02 | Execute Python (sum 1-10) | ✅ PASS | {
| S5 | S5-03 | Execute Python (list comprehension) | ✅ PASS | {
| S6 | S6-01 | auto-security routing | ⚠️  WARN | signals: ['sql', 'inject'] \| ROUTING MISMATCH: got qwen3.5:9b, expected Ollama: | 28.6s |
| S6 | S6-02 | auto-redteam routing | ⚠️  WARN | signals: ['recon', 'scan', 'exploit'] \| ROUTING MISMATCH: got deepseek-r1:32b-q | 56.0s |
| S6 | S6-03 | auto-blueteam routing | ✅ PASS | signals: ['isolate', 'contain', 'backup'] \| routed -> hf.co/fdtn-ai/Foundation- | 17.6s |
| S6 | S6-04 | Content-aware security routing | ✅ PASS | routed to security workspace: True | 31.9s |
| S7 | S7-01 | Music MCP health | ✅ PASS | service: music-mcp | 0.0s |
| S7 | S7-02 | Generate music (5s jazz) | ✅ PASS | {
| S8 | S8-01 | MLX Speech health | ✅ PASS | voice_cloning: True | 0.0s |
| S8 | S8-02 | MLX Speech TTS | ✅ PASS | duration: 2.85s | 3.0s |
| S9 | S9-01 | MLX Speech ASR available | ✅ PASS | Qwen3-ASR | 0.0s |
| S9 | S9-03 | MLX Transcribe health | ℹ️  INFO | not running (start with ./launch.sh start-transcribe) | 0.0s |
| S9 | S9-04 | MLX Transcribe diarization | ℹ️  INFO | service not running | 0.0s |
| S9 | S9-05 | Workspace upload resolution | ℹ️  INFO | service not running | 0.0s |
| S10 | S10-01 | Persona itexpert | ✅ PASS | signals: ['diagnose', 'gather', 'troubleshoot'] \| routed -> huihui_ai/qwen3.5-a | 12.1s |
| S10 | S10-02 | Persona techreviewer | ✅ PASS | signals: ['feature', 'review'] \| routed -> huihui_ai/qwen3.5-abliterated:9b mat | 7.3s |
| S10 | S10-03 | Persona webnavigator | ✅ PASS | signals: ['source'] \| routed -> huihui_ai/qwen3.5-abliterated:9b matches via wo | 7.3s |
| S10 | S10-04 | Persona agentorchestrator | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> qwen3-coder-next matches via wor | 39.1s |
| S10 | S10-05 | Persona codebasewikidocumentationskill | ✅ PASS | signals: ['Args', 'str', 'dict'] \| routed -> qwen3-coder-next matches via works | 17.2s |
| S10 | S10-06 | Persona blueteamdefender | ✅ PASS | signals: ['encrypt', 'extension', 'ransom'] \| routed -> hf.co/fdtn-ai/Foundatio | 15.8s |
| S10 | S10-07 | Persona bugdiscoverycodeassistant | ✅ PASS | signals: ['indexerror', 'out of range', 'empty list'] \| routed -> qwen3-coder:3 | 22.1s |
| S10 | S10-08 | Persona codereviewassistant | ✅ PASS | signals: ['list', 'comprehension'] \| routed -> qwen3-coder:30b-a3b-q4_K_M match | 4.9s |
| S10 | S10-09 | Persona codereviewer | ✅ PASS | signals: ['==', 'bool', 'True'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches  | 6.4s |
| S10 | S10-10 | Persona creativecoder | ✅ PASS | signals: ['canvas', 'ball', 'click'] \| routed -> qwen3-coder:30b-a3b-q4_K_M mat | 11.2s |
| S10 | S10-11 | Persona devopsautomator | ✅ PASS | signals: ['#!/', 'bash', 'date'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches | 6.6s |
| S10 | S10-12 | Persona e2edebugger | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> qwen3-coder:30b-a3b-q4_K_M match | 8.1s |
| S10 | S10-13 | Persona e2etestauthor | ✅ PASS | signals: ['stage'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via workspace | 9.2s |
| S10 | S10-14 | Persona ethereumdeveloper | ✅ PASS | signals: ['contract', 'pragma', 'solidity'] \| routed -> qwen3-coder:30b-a3b-q4_ | 4.1s |
| S10 | S10-15 | Persona excelsheet | ✅ PASS | signals: ['VLOOKUP', 'formula', 'range'] \| routed -> qwen3-coder:30b-a3b-q4_K_M | 5.4s |
| S10 | S10-16 | Persona formfiller | ⚠️  WARN | no signals in:  \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via workspace 'a | 6.5s |
| S10 | S10-17 | Persona fullstacksoftwaredeveloper | ✅ PASS | signals: ['REST', 'API'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via wor | 6.5s |
| S10 | S10-18 | Persona githubexpert | ✅ PASS | signals: ['rebase', 'merge', 'history'] \| routed -> qwen3-coder:30b-a3b-q4_K_M  | 6.5s |
| S10 | S10-19 | Persona goengineer | ✅ PASS | signals: ['middleware', 'http.handler', 'context'] \| routed -> qwen3-coder:30b- | 11.3s |
| S10 | S10-20 | Persona javascriptconsole | ✅ PASS | signals: ['Math', 'PI'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via work | 2.4s |
| S10 | S10-21 | Persona kubernetesdockerrpglearningengin | ✅ PASS | signals: ['layer', 'image', 'build'] \| routed -> qwen3-coder:30b-a3b-q4_K_M mat | 6.4s |
| S10 | S10-22 | Persona linuxterminal | ✅ PASS | signals: ['total', 'user', '-rw'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matche | 6.5s |
| S10 | S10-23 | Persona pythoncodegeneratorcleanoptimize | ✅ PASS | signals: ['sorted', 'key', 'dict'] \| routed -> qwen3-coder:30b-a3b-q4_K_M match | 6.5s |
| S10 | S10-24 | Persona pythoninterpreter | ✅ PASS | signals: ['[3, 2, 1]', '3, 2, 1'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matche | 2.4s |
| S10 | S10-25 | Persona rustengineer | ✅ PASS | signals: ['arc', 'lru', 'instant'] \| routed -> qwen3-coder:30b-a3b-q4_K_M match | 11.2s |
| S10 | S10-26 | Persona seniorfrontenddeveloper | ✅ PASS | signals: ['useState', 'useEffect', 'hook'] \| routed -> qwen3-coder:30b-a3b-q4_K | 8.7s |
| S10 | S10-27 | Persona softwarequalityassurancetester | ⚠️  WARN | no signals in:  \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via workspace 'a | 6.4s |
| S10 | S10-28 | Persona sqlterminal | ✅ PASS | signals: ['SELECT', 'FROM', 'WHERE'] \| routed -> qwen3-coder:30b-a3b-q4_K_M mat | 2.6s |
| S10 | S10-29 | Persona terraformwriter | ⚠️  WARN | no signals in:  \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via workspace 'a | 6.4s |
| S10 | S10-30 | Persona typescriptengineer | ✅ PASS | signals: ['discriminated union', 'type', 'loading'] \| routed -> qwen3-coder:30b | 6.5s |
| S10 | S10-31 | Persona ux-uideveloper | ✅ PASS | signals: ['mobile'] \| routed -> qwen3-coder:30b-a3b-q4_K_M matches via workspac | 2.4s |
| S10 | S10-32 | Persona creativewriter | ✅ PASS | signals: ['rain', 'detective', 'dark'] \| routed -> fredrezones55/Qwen3.6-35B-A3 | 15.6s |
| S10 | S10-33 | Persona hermes3writer | ✅ PASS | signals: ['detective', 'coastal', 'town'] \| routed -> fredrezones55/Qwen3.6-35B | 5.1s |
| S10 | S10-34 | Persona interviewcoach | ✅ PASS | signals: ['star', 'behavioral'] \| routed -> fredrezones55/Qwen3.6-35B-A3B-Uncen | 5.2s |
| S10 | S10-35 | Persona proofreader | ✅ PASS | signals: ['address'] \| routed -> fredrezones55/Qwen3.6-35B-A3B-Uncensored match | 5.2s |
| S10 | S10-36 | Persona dailydriver | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-37 | Persona personalassistant | ✅ PASS | signals: ['step', 'plan', 'stage'] \| routed -> gemma4:26b-a4b-it-qat matches vi | 18.0s |
| S10 | S10-38 | Persona dashboardarchitect | ✅ PASS | signals: ['mrr', 'above the fold'] \| routed -> deepseek-r1:32b-q8_0 matches via | 56.1s |
| S10 | S10-39 | Persona dataanalyst | ✅ PASS | signals: ['correlation', 'causation', 'variable'] \| routed -> deepseek-r1:32b-q | 38.1s |
| S10 | S10-40 | Persona databasearchitect | ✅ PASS | signals: ['users', 'organizations', 'tenant'] \| routed -> deepseek-r1:32b-q8_0  | 37.4s |
| S10 | S10-41 | Persona dataextractor | ✅ PASS | signals: ['field', 'value'] \| routed -> deepseek-r1:32b-q8_0 matches via worksp | 37.2s |
| S10 | S10-42 | Persona datascientist | ✅ PASS | signals: ['feature', 'normalize', 'engineer'] \| routed -> deepseek-r1:32b-q8_0  | 36.8s |
| S10 | S10-43 | Persona machinelearningengineer | ✅ PASS | signals: ['gradient', 'descent', 'learning'] \| routed -> deepseek-r1:32b-q8_0 m | 37.5s |
| S10 | S10-44 | Persona statistician | ✅ PASS | signals: ['p-value', 'null', 'hypothesis'] \| routed -> deepseek-r1:32b-q8_0 mat | 37.6s |
| S10 | S10-45 | Persona documentationarchitect | ⚠️  WARN | no signals in:  \| routed -> granite4.1:8b matches via workspace 'auto-documents | 13.6s |
| S10 | S10-46 | Persona phi4specialist | ⚠️  WARN | no signals in:  \| routed -> granite4.1:8b matches via workspace 'auto-documents | 9.2s |
| S10 | S10-47 | Persona techwriter | ✅ PASS | signals: ['endpoint', 'request', 'response'] \| routed -> granite4.1:8b matches  | 7.7s |
| S10 | S10-48 | Persona transcriptanalyst | ℹ️  INFO | excluded from text-prompt smoke (attachment-driven) | 0.0s |
| S10 | S10-49 | Persona mathreasoner | ✅ PASS | signals: ['eigenvalue', 'det', 'lambda'] \| routed -> phi4-mini-reasoning matche | 7.0s |
| S10 | S10-50 | Persona magistralstrategist | ✅ PASS | signals: ['milestone', 'KPI', 'launch'] \| routed -> hf.co/unsloth/Magistral-Sma | 38.1s |
| S10 | S10-51 | Persona phi4stemanalyst | ⚠️  WARN | signals: ['pythagor', 'triangle', 'hypotenuse'] \| ROUTING MISMATCH: got dolphin | 9.7s |
| S10 | S10-52 | Persona businessanalyst | ✅ PASS | signals: ['stakeholder', 'process'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528- | 9.7s |
| S10 | S10-53 | Persona devopsengineer | ✅ PASS | signals: ['pod', 'pending', 'running'] \| routed -> hf.co/unsloth/DeepSeek-R1-05 | 6.4s |
| S10 | S10-54 | Persona gptossanalyst | ✅ PASS | signals: ['trade', 'scale', 'deploy'] \| routed -> hf.co/unsloth/DeepSeek-R1-052 | 6.5s |
| S10 | S10-55 | Persona itarchitect | ✅ PASS | signals: ['availability'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-  | 6.5s |
| S10 | S10-56 | Persona productmanager | ✅ PASS | signals: ['problem', 'success metric'] \| routed -> hf.co/unsloth/DeepSeek-R1-05 | 6.6s |
| S10 | S10-57 | Persona seniorsoftwareengineersoftwarear | ✅ PASS | signals: ['pattern', 'queue', 'scale'] \| routed -> hf.co/unsloth/DeepSeek-R1-05 | 6.4s |
| S10 | S10-58 | Persona pentester | ✅ PASS | signals: ['OWASP'] \| routed -> baronllm:q6_k matches via workspace 'auto-redtea | 13.2s |
| S10 | S10-59 | Persona redteamoperator | ⚠️  WARN | signals: ['exploit', 'technique'] \| ROUTING MISMATCH: got dolphin-llama3:8b, ex | 7.0s |
| S10 | S10-60 | Persona factchecker | ✅ PASS | signals: ['source'] \| routed -> huihui_ai/tongyi-deepresearch-abliterate matche | 20.8s |
| S10 | S10-61 | Persona gemmaresearchanalyst | ✅ PASS | signals: ['method', 'data', 'collect'] \| routed -> huihui_ai/tongyi-deepresearc | 5.4s |
| S10 | S10-62 | Persona kbnavigator | ✅ PASS | signals: ['search', 'query', 'results'] \| routed -> huihui_ai/tongyi-deepresear | 7.3s |
| S10 | S10-63 | Persona marketanalyst | ✅ PASS | signals: ['trend', 'growth', 'revenue'] \| routed -> huihui_ai/tongyi-deepresear | 5.5s |
| S10 | S10-64 | Persona paywalledresearcher | ✅ PASS | signals: ['source', 'url'] \| routed -> huihui_ai/tongyi-deepresearch-abliterate | 7.0s |
| S10 | S10-65 | Persona researchanalyst | ✅ PASS | signals: ['systematic', 'search', 'inclusion'] \| routed -> huihui_ai/tongyi-dee | 5.4s |
| S10 | S10-66 | Persona supergemma4researcher | ✅ PASS | signals: ['OSINT', 'search', 'verify'] \| routed -> huihui_ai/tongyi-deepresearc | 6.6s |
| S10 | S10-67 | Persona webresearcher | ✅ PASS | signals: ['source', 'url'] \| routed -> huihui_ai/tongyi-deepresearch-abliterate | 5.5s |
| S10 | S10-68 | Persona cybersecurityspecialist | ⚠️  WARN | signals: ['zero', 'trust', 'verify'] \| ROUTING MISMATCH: got qwen3.5:9b, expect | 18.5s |
| S10 | S10-69 | Persona networkengineer | ⚠️  WARN | signals: ['vlan', 'access', 'GigabitEthernet'] \| ROUTING MISMATCH: got qwen3-vl | 67.5s |
| S10 | S10-70 | Persona splunkdetectionauthor | ✅ PASS | signals: ['tstats', 'authentication', 't1110'] \| routed -> hf.co/bartowski/huih | 31.8s |
| S10 | S10-71 | Persona splunksplgineer | ✅ PASS | signals: ['stats', 'count', 'fail'] \| routed -> hf.co/bartowski/huihui-ai_Qwen3 | 8.7s |
| S10 | S10-72 | Persona chartanalyst | ✅ PASS | signals: ['quarter', 'revenue'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528-Qwen | 9.9s |
| S10 | S10-73 | Persona codescreenshotreader | ✅ PASS | signals: ['function', 'code'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528-Qwen3- | 6.4s |
| S10 | S10-74 | Persona diagramreader | ✅ PASS | signals: ['relationships', 'components', 'abstraction'] \| routed -> hf.co/unslo | 6.3s |
| S10 | S10-75 | Persona gemma4e4bvision | ✅ PASS | signals: ['stack', 'trace', 'error'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528 | 6.4s |
| S10 | S10-76 | Persona gemma4jangvision | ✅ PASS | signals: ['credential', 'password', 'screenshot'] \| routed -> hf.co/unsloth/Dee | 6.5s |
| S10 | S10-77 | Persona ocrspecialist | ✅ PASS | signals: ['receipt', 'layout'] \| routed -> hf.co/unsloth/DeepSeek-R1-0528-Qwen3 | 6.3s |
| S10 | S10-78 | Persona whiteboardconverter | ✅ PASS | signals: ['entities', 'relationships'] \| routed -> hf.co/unsloth/DeepSeek-R1-05 | 6.4s |
| S10 | S10-79 | Persona bench-devstral | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-80 | Persona bench-devstral-small-2 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-81 | Persona bench-dolphin8b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-82 | Persona bench-foundation-sec | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-83 | Persona bench-gemma4-12b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-84 | Persona bench-gemma4-26b-optiq | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-85 | Persona bench-gemma4-26b-qat | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-86 | Persona bench-gemma4-31b-qat | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-87 | Persona bench-gemma4-e2b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-88 | Persona bench-gemma4-e4b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-89 | Persona bench-gemma4-e4b-qat | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-90 | Persona bench-glm | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-91 | Persona bench-gptoss | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-92 | Persona bench-granite-speech | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-93 | Persona bench-granite41-30b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-94 | Persona bench-granite41-8b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-95 | Persona bench-harness1 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-96 | Persona bench-huihui-qwen36-27b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-97 | Persona bench-huihui-qwen36-35b-a3b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-98 | Persona bench-laguna | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-99 | Persona bench-lfm2-moe | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-100 | Persona bench-lfm25-8b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-101 | Persona bench-lfm25-8b-uncensored | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-102 | Persona bench-llama33-70b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-103 | Persona bench-mistral-small32 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-104 | Persona bench-nanonets-ocr2 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-105 | Persona bench-negentropy | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-106 | Persona bench-nex-n2-mini | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-107 | Persona bench-olmo3-32b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-108 | Persona bench-olmocr2 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-109 | Persona bench-omnicoder2 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-110 | Persona bench-phi4 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-111 | Persona bench-phi4-mini | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-112 | Persona bench-phi4-mini-reasoning | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-113 | Persona bench-phi4-reasoning | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-114 | Persona bench-qwen3-coder-30b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-115 | Persona bench-qwen3-coder-next | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-116 | Persona bench-qwen3-coder-next-abliterat | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-117 | Persona bench-qwen35-abliterated | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-118 | Persona bench-qwen36-27b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-119 | Persona bench-qwen36-27b-mtp | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-120 | Persona bench-qwen36-27b-optiq | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-121 | Persona bench-qwen36-27b-ud | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-122 | Persona bench-qwen36-35b-a3b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-123 | Persona bench-qwen36-35b-a3b-ud | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-124 | Persona bench-qwen36-hauhaucs | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-125 | Persona bench-r1-0528-abliterated | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-126 | Persona bench-r1-0528-qwen3-8b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-127 | Persona bench-starcoder2 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-128 | Persona bench-toolace25 | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-129 | Persona bench-voxtral-realtime | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-130 | Persona bench-voxtral-tts | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-131 | Persona bench-qwen36-abl-27b | ❌ FAIL | no PERSONA_PROMPTS entry  [UNCLASSIFIED] | 0.0s |
| S10 | S10-132 | Persona toolcomposer | ✅ PASS | signals: ['execute_python', 'remember', 'read'] \| routed -> granite4.1:8b match | 16.1s |
| S10c | S10c-00 | fixture loaded | ✅ PASS | 317 concrete scenarios across compliance personas | 0.0s |
| S10c | S10c-001 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 21.5s |
| S10c | S10c-002 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 22.7s |
| S10c | S10c-003 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 17.3s |
| S10c | S10c-004 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 18.1s |
| S10c | S10c-005 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 22.3s |
| S10c | S10c-006 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 16.0s |
| S10c | S10c-007 | cippolicywriter/gap-analysis-table-struc | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 16.0s |
| S10c | S10c-008 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 1.9s |
| S10c | S10c-009 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.1s |
| S10c | S10c-010 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.0s |
| S10c | S10c-011 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 1.8s |
| S10c | S10c-012 | cippolicywriter/classification-token-dis | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 1.9s |
| S10c | S10c-013 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 1.9s |
| S10c | S10c-014 | cippolicywriter/classification-token-dis | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.0s |
| S10c | S10c-015 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 8.4s |
| S10c | S10c-016 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 9.1s |
| S10c | S10c-017 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.3s |
| S10c | S10c-018 | cippolicywriter/anti-fabrication-verbati | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b  [UNCLASSIF | 8.6s |
| S10c | S10c-019 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 16.8s |
| S10c | S10c-020 | cippolicywriter/anti-fabrication-verbati | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 12.6s |
| S10c | S10c-021 | cippolicywriter/anti-fabrication-verbati | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 13.0s |
| S10c | S10c-022 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 10.1s |
| S10c | S10c-023 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.5s |
| S10c | S10c-024 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 6.4s |
| S10c | S10c-025 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.6s |
| S10c | S10c-026 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 6.2s |
| S10c | S10c-027 | cippolicywriter/refuse-to-certify-binary | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 3.5s |
| S10c | S10c-028 | cippolicywriter/refuse-to-certify-binary | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 8.6s |
| S10c | S10c-029 | cippolicywriter/insufficient-context-vag | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 10.8s |
| S10c | S10c-030 | cippolicywriter/policy-modal-verbs[NERC_ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.6s |
| S10c | S10c-031 | cippolicywriter/policy-modal-verbs[HIPAA | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.4s |
| S10c | S10c-032 | cippolicywriter/policy-modal-verbs[GDPR] | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.9s |
| S10c | S10c-033 | cippolicywriter/policy-modal-verbs[SOC2] | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 9.6s |
| S10c | S10c-034 | cippolicywriter/policy-modal-verbs[PCI_D | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 6.3s |
| S10c | S10c-035 | cippolicywriter/policy-modal-verbs[NIST_ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.4s |
| S10c | S10c-036 | cippolicywriter/policy-modal-verbs[ISO_2 | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 11.0s |
| S10c | S10c-037 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 8.6s |
| S10c | S10c-038 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.7s |
| S10c | S10c-039 | cippolicywriter/citation-format-discipli | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.8s |
| S10c | S10c-040 | cippolicywriter/citation-format-discipli | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 7.2s |
| S10c | S10c-041 | cippolicywriter/citation-format-discipli | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 4.1s |
| S10c | S10c-042 | cippolicywriter/citation-format-discipli | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 4.3s |
| S10c | S10c-043 | cippolicywriter/citation-format-discipli | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 9.1s |
| S10c | S10c-044 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 14.4s |
| S10c | S10c-045 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.7s |
| S10c | S10c-046 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 12.9s |
| S10c | S10c-047 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 13.0s |
| S10c | S10c-048 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 12.3s |
| S10c | S10c-049 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.5s |
| S10c | S10c-050 | cippolicywriter/dense-structured-tool-ou | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.3s |
| S10c | S10c-051 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 7.0s |
| S10c | S10c-052 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.7s |
| S10c | S10c-053 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-054 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-055 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.9s |
| S10c | S10c-056 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 5.5s |
| S10c | S10c-057 | complianceanalyst/gap-analysis-table-str | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.3s |
| S10c | S10c-058 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.2s |
| S10c | S10c-059 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 5.3s |
| S10c | S10c-060 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.8s |
| S10c | S10c-061 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.6s |
| S10c | S10c-062 | complianceanalyst/classification-token-d | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.4s |
| S10c | S10c-063 | complianceanalyst/classification-token-d | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.3s |
| S10c | S10c-064 | complianceanalyst/classification-token-d | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.0s |
| S10c | S10c-065 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 16.0s |
| S10c | S10c-066 | complianceanalyst/anti-fabrication-verba | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b  [UNCLASSIF | 7.5s |
| S10c | S10c-067 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 3.5s |
| S10c | S10c-068 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.7s |
| S10c | S10c-069 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.6s |
| S10c | S10c-070 | complianceanalyst/anti-fabrication-verba | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.9s |
| S10c | S10c-071 | complianceanalyst/anti-fabrication-verba | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 8.7s |
| S10c | S10c-072 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.8s |
| S10c | S10c-073 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 9.3s |
| S10c | S10c-074 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 9.1s |
| S10c | S10c-075 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.6s |
| S10c | S10c-076 | complianceanalyst/refuse-to-certify-bina | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 5.0s |
| S10c | S10c-077 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 14.5s |
| S10c | S10c-078 | complianceanalyst/refuse-to-certify-bina | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 9.1s |
| S10c | S10c-079 | complianceanalyst/insufficient-context-v | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 15.5s |
| S10c | S10c-080 | complianceanalyst/policy-modal-verbs[NER | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 26.5s |
| S10c | S10c-081 | complianceanalyst/policy-modal-verbs[HIP | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=granite4.1:8b  [UNCLASSIFIE | 9.3s |
| S10c | S10c-082 | complianceanalyst/policy-modal-verbs[GDP | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=granite4.1:8b  [UNCLASSIFIE | 8.9s |
| S10c | S10c-083 | complianceanalyst/policy-modal-verbs[SOC | ⚠️  WARN | MUSTs OK; SHOULD failed: policy.modal_verbs \| model=granite4.1:8b  [UNCLASSIFIE | 7.7s |
| S10c | S10c-084 | complianceanalyst/policy-modal-verbs[PCI | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 12.0s |
| S10c | S10c-085 | complianceanalyst/policy-modal-verbs[NIS | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 12.1s |
| S10c | S10c-086 | complianceanalyst/policy-modal-verbs[ISO | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 12.7s |
| S10c | S10c-087 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 8.5s |
| S10c | S10c-088 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.0s |
| S10c | S10c-089 | complianceanalyst/citation-format-discip | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.4s |
| S10c | S10c-090 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 3.9s |
| S10c | S10c-091 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 3.4s |
| S10c | S10c-092 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 5.0s |
| S10c | S10c-093 | complianceanalyst/citation-format-discip | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 3.9s |
| S10c | S10c-094 | complianceanalyst/cross-framework-mappin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53], citation.format[ISO_27001 | 8.2s |
| S10c | S10c-095 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 16.2s |
| S10c | S10c-096 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.2s |
| S10c | S10c-097 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 16.9s |
| S10c | S10c-098 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 12.4s |
| S10c | S10c-099 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.6s |
| S10c | S10c-100 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.3s |
| S10c | S10c-101 | complianceanalyst/dense-structured-tool- | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.4s |
| S10c | S10c-102 | complianceanalyst/long-context-multi-cit | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53], citation.format[ISO_27001 | 22.0s |
| S10c | S10c-103 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 17.6s |
| S10c | S10c-104 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.7s |
| S10c | S10c-105 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 16.0s |
| S10c | S10c-106 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.0s |
| S10c | S10c-107 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-108 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 21.0s |
| S10c | S10c-109 | gdprdpoadvisor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-110 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.1s |
| S10c | S10c-111 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 1.7s |
| S10c | S10c-112 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 5.4s |
| S10c | S10c-113 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 1.6s |
| S10c | S10c-114 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.3s |
| S10c | S10c-115 | gdprdpoadvisor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.1s |
| S10c | S10c-116 | gdprdpoadvisor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 1.8s |
| S10c | S10c-117 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 12.6s |
| S10c | S10c-118 | gdprdpoadvisor/anti-fabrication-verbatim | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b  [UNCLASSIF | 6.9s |
| S10c | S10c-119 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 2.2s |
| S10c | S10c-120 | gdprdpoadvisor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 11.1s |
| S10c | S10c-121 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 12.2s |
| S10c | S10c-122 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.0s |
| S10c | S10c-123 | gdprdpoadvisor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 16.0s |
| S10c | S10c-124 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 16.0s |
| S10c | S10c-125 | gdprdpoadvisor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 8.0s |
| S10c | S10c-126 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 7.2s |
| S10c | S10c-127 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 3.5s |
| S10c | S10c-128 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 20.4s |
| S10c | S10c-129 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.0s |
| S10c | S10c-130 | gdprdpoadvisor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 6.8s |
| S10c | S10c-131 | gdprdpoadvisor/insufficient-context-vagu | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 7.4s |
| S10c | S10c-132 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=granite4.1:8b  [UNCL | 4.2s |
| S10c | S10c-133 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.4s |
| S10c | S10c-134 | gdprdpoadvisor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.7s |
| S10c | S10c-135 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 14.3s |
| S10c | S10c-136 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 4.1s |
| S10c | S10c-137 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 3.2s |
| S10c | S10c-138 | gdprdpoadvisor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 4.3s |
| S10c | S10c-139 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 16.5s |
| S10c | S10c-140 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 21.8s |
| S10c | S10c-141 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 13.0s |
| S10c | S10c-142 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.4s |
| S10c | S10c-143 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.1s |
| S10c | S10c-144 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.9s |
| S10c | S10c-145 | gdprdpoadvisor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.0s |
| S10c | S10c-146 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 22.3s |
| S10c | S10c-147 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.7s |
| S10c | S10c-148 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.1s |
| S10c | S10c-149 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.1s |
| S10c | S10c-150 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 18.8s |
| S10c | S10c-151 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 21.2s |
| S10c | S10c-152 | hipaaprivacyofficer/gap-analysis-table-s | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-153 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.2s |
| S10c | S10c-154 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 1.8s |
| S10c | S10c-155 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 6.0s |
| S10c | S10c-156 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.4s |
| S10c | S10c-157 | hipaaprivacyofficer/classification-token | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.4s |
| S10c | S10c-158 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 6.5s |
| S10c | S10c-159 | hipaaprivacyofficer/classification-token | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.0s |
| S10c | S10c-160 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 11.2s |
| S10c | S10c-161 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 7.0s |
| S10c | S10c-162 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 3.1s |
| S10c | S10c-163 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 9.2s |
| S10c | S10c-164 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 7.2s |
| S10c | S10c-165 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.1s |
| S10c | S10c-166 | hipaaprivacyofficer/anti-fabrication-ver | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.0s |
| S10c | S10c-167 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 7.1s |
| S10c | S10c-168 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.7s |
| S10c | S10c-169 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 7.0s |
| S10c | S10c-170 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.3s |
| S10c | S10c-171 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 9.1s |
| S10c | S10c-172 | hipaaprivacyofficer/refuse-to-certify-bi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 12.3s |
| S10c | S10c-173 | hipaaprivacyofficer/refuse-to-certify-bi | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.0s |
| S10c | S10c-174 | hipaaprivacyofficer/insufficient-context | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 10.0s |
| S10c | S10c-175 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=granite4.1:8b  [UNCL | 5.0s |
| S10c | S10c-176 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.1s |
| S10c | S10c-177 | hipaaprivacyofficer/citation-format-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.1s |
| S10c | S10c-178 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 4.9s |
| S10c | S10c-179 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 4.0s |
| S10c | S10c-180 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 3.2s |
| S10c | S10c-181 | hipaaprivacyofficer/citation-format-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 6.5s |
| S10c | S10c-182 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 16.5s |
| S10c | S10c-183 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.7s |
| S10c | S10c-184 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.2s |
| S10c | S10c-185 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.7s |
| S10c | S10c-186 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.9s |
| S10c | S10c-187 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.2s |
| S10c | S10c-188 | hipaaprivacyofficer/dense-structured-too | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.6s |
| S10c | S10c-189 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 22.5s |
| S10c | S10c-190 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 16.0s |
| S10c | S10c-191 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 15.9s |
| S10c | S10c-192 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.1s |
| S10c | S10c-193 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 15.9s |
| S10c | S10c-194 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.8s |
| S10c | S10c-195 | nerccipcomplianceanalyst/gap-analysis-ta | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.7s |
| S10c | S10c-196 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.2s |
| S10c | S10c-197 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.4s |
| S10c | S10c-198 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 1.8s |
| S10c | S10c-199 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.3s |
| S10c | S10c-200 | nerccipcomplianceanalyst/classification- | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.3s |
| S10c | S10c-201 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.2s |
| S10c | S10c-202 | nerccipcomplianceanalyst/classification- | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.0s |
| S10c | S10c-203 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 17.0s |
| S10c | S10c-204 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 3.5s |
| S10c | S10c-205 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 2.1s |
| S10c | S10c-206 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 13.5s |
| S10c | S10c-207 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.2s |
| S10c | S10c-208 | nerccipcomplianceanalyst/anti-fabricatio | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 9.5s |
| S10c | S10c-209 | nerccipcomplianceanalyst/anti-fabricatio | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 6.5s |
| S10c | S10c-210 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.3s |
| S10c | S10c-211 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 7.1s |
| S10c | S10c-212 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 9.6s |
| S10c | S10c-213 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 2.8s |
| S10c | S10c-214 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.8s |
| S10c | S10c-215 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 6.5s |
| S10c | S10c-216 | nerccipcomplianceanalyst/refuse-to-certi | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 5.4s |
| S10c | S10c-217 | nerccipcomplianceanalyst/insufficient-co | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 12.6s |
| S10c | S10c-218 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.9s |
| S10c | S10c-219 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.8s |
| S10c | S10c-220 | nerccipcomplianceanalyst/citation-format | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.5s |
| S10c | S10c-221 | nerccipcomplianceanalyst/citation-format | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 3.7s |
| S10c | S10c-222 | nerccipcomplianceanalyst/citation-format | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 2.7s |
| S10c | S10c-223 | nerccipcomplianceanalyst/citation-format | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 3.7s |
| S10c | S10c-224 | nerccipcomplianceanalyst/citation-format | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 4.8s |
| S10c | S10c-225 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 12.5s |
| S10c | S10c-226 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 3.6s |
| S10c | S10c-227 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 13.2s |
| S10c | S10c-228 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.3s |
| S10c | S10c-229 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.4s |
| S10c | S10c-230 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 13.2s |
| S10c | S10c-231 | nerccipcomplianceanalyst/dense-structure | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.9s |
| S10c | S10c-232 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 22.1s |
| S10c | S10c-233 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.6s |
| S10c | S10c-234 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.1s |
| S10c | S10c-235 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.0s |
| S10c | S10c-236 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.7s |
| S10c | S10c-237 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 5.7s |
| S10c | S10c-238 | pcidssassessor/gap-analysis-table-struct | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 5.7s |
| S10c | S10c-239 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 3.2s |
| S10c | S10c-240 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 7.0s |
| S10c | S10c-241 | pcidssassessor/classification-token-disc | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 1.9s |
| S10c | S10c-242 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.2s |
| S10c | S10c-243 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.1s |
| S10c | S10c-244 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 2.1s |
| S10c | S10c-245 | pcidssassessor/classification-token-disc | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 8.7s |
| S10c | S10c-246 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.1s |
| S10c | S10c-247 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 2.1s |
| S10c | S10c-248 | pcidssassessor/anti-fabrication-verbatim | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.6s |
| S10c | S10c-249 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.1s |
| S10c | S10c-250 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.0s |
| S10c | S10c-251 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.1s |
| S10c | S10c-252 | pcidssassessor/anti-fabrication-verbatim | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 6.9s |
| S10c | S10c-253 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 6.7s |
| S10c | S10c-254 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 8.5s |
| S10c | S10c-255 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 3.6s |
| S10c | S10c-256 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.2s |
| S10c | S10c-257 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 19.0s |
| S10c | S10c-258 | pcidssassessor/refuse-to-certify-binary[ | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 13.0s |
| S10c | S10c-259 | pcidssassessor/refuse-to-certify-binary[ | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.6s |
| S10c | S10c-260 | pcidssassessor/insufficient-context-vagu | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 9.3s |
| S10c | S10c-261 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=granite4.1:8b  [UNCL | 5.2s |
| S10c | S10c-262 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[HIPAA] \| model=granite4.1:8b  [UNCLASS | 3.7s |
| S10c | S10c-263 | pcidssassessor/citation-format-disciplin | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 5.0s |
| S10c | S10c-264 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 4.5s |
| S10c | S10c-265 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 4.0s |
| S10c | S10c-266 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 4.8s |
| S10c | S10c-267 | pcidssassessor/citation-format-disciplin | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 4.0s |
| S10c | S10c-268 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 14.4s |
| S10c | S10c-269 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.8s |
| S10c | S10c-270 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.5s |
| S10c | S10c-271 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.9s |
| S10c | S10c-272 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 8.1s |
| S10c | S10c-273 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 6.9s |
| S10c | S10c-274 | pcidssassessor/dense-structured-tool-out | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.6s |
| S10c | S10c-275 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 21.9s |
| S10c | S10c-276 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 15.9s |
| S10c | S10c-277 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.0s |
| S10c | S10c-278 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.2s |
| S10c | S10c-279 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.3s |
| S10c | S10c-280 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.3s |
| S10c | S10c-281 | soc2auditor/gap-analysis-table-structure | ⚠️  WARN | MUSTs OK; SHOULD failed: structural.table_columns, classification.exact_token \| | 20.4s |
| S10c | S10c-282 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 8.1s |
| S10c | S10c-283 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 3.0s |
| S10c | S10c-284 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 6.0s |
| S10c | S10c-285 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 4.6s |
| S10c | S10c-286 | soc2auditor/classification-token-discipl | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 2.2s |
| S10c | S10c-287 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 3.2s |
| S10c | S10c-288 | soc2auditor/classification-token-discipl | ⚠️  WARN | MUSTs OK; SHOULD failed: classification.exact_token \| model=granite4.1:8b  [UNC | 6.1s |
| S10c | S10c-289 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 8.1s |
| S10c | S10c-290 | soc2auditor/anti-fabrication-verbatim-te | ❌ FAIL | MUST failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b  [UNCLASSIF | 9.6s |
| S10c | S10c-291 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 10.6s |
| S10c | S10c-292 | soc2auditor/anti-fabrication-verbatim-te | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 12.2s |
| S10c | S10c-293 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.5s |
| S10c | S10c-294 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 5.9s |
| S10c | S10c-295 | soc2auditor/anti-fabrication-verbatim-te | ⚠️  WARN | MUSTs OK; SHOULD failed: anti_fabrication.refusal_pattern \| model=granite4.1:8b | 11.8s |
| S10c | S10c-296 | soc2auditor/refuse-to-certify-binary[NER | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 10.4s |
| S10c | S10c-297 | soc2auditor/refuse-to-certify-binary[HIP | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 9.5s |
| S10c | S10c-298 | soc2auditor/refuse-to-certify-binary[GDP | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 4.5s |
| S10c | S10c-299 | soc2auditor/refuse-to-certify-binary[SOC | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 8.7s |
| S10c | S10c-300 | soc2auditor/refuse-to-certify-binary[PCI | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 7.8s |
| S10c | S10c-301 | soc2auditor/refuse-to-certify-binary[NIS | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 14.3s |
| S10c | S10c-302 | soc2auditor/refuse-to-certify-binary[ISO | ⚠️  WARN | MUSTs OK; SHOULD failed: refuse_to_certify \| model=granite4.1:8b  [UNCLASSIFIED | 12.9s |
| S10c | S10c-303 | soc2auditor/insufficient-context-vague-p | ⚠️  WARN | MUSTs OK; SHOULD failed: insufficient_context.exact_phrase \| model=granite4.1:8 | 11.1s |
| S10c | S10c-304 | soc2auditor/citation-format-discipline[N | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NERC_CIP] \| model=granite4.1:8b  [UNCL | 5.3s |
| S10c | S10c-305 | soc2auditor/citation-format-discipline[H | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[HIPAA] \| model=granite4.1:8b  [UNCLASS | 4.6s |
| S10c | S10c-306 | soc2auditor/citation-format-discipline[G | ✅ PASS | all 1 assertions OK \| model=granite4.1:8b | 4.1s |
| S10c | S10c-307 | soc2auditor/citation-format-discipline[S | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[SOC2] \| model=granite4.1:8b  [UNCLASSI | 3.6s |
| S10c | S10c-308 | soc2auditor/citation-format-discipline[P | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[PCI_DSS] \| model=granite4.1:8b  [UNCLA | 4.2s |
| S10c | S10c-309 | soc2auditor/citation-format-discipline[N | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[NIST_800_53] \| model=granite4.1:8b  [U | 4.1s |
| S10c | S10c-310 | soc2auditor/citation-format-discipline[I | ⚠️  WARN | MUSTs OK; SHOULD failed: citation.format[ISO_27001] \| model=granite4.1:8b  [UNC | 3.5s |
| S10c | S10c-311 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 12.6s |
| S10c | S10c-312 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 13.1s |
| S10c | S10c-313 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.6s |
| S10c | S10c-314 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.9s |
| S10c | S10c-315 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 10.1s |
| S10c | S10c-316 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 11.2s |
| S10c | S10c-317 | soc2auditor/dense-structured-tool-output | ✅ PASS | all 2 assertions OK \| model=granite4.1:8b | 9.3s |
| S12 | S12-01 | SearXNG search | ✅ PASS | 19 results | 0.7s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.1s |
| S15 | S15-01 | Workspace root exists | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-02 | Workspace subdirectories | ✅ PASS | all present | 0.0s |
| S15 | S15-03 | OWUI uploads bind mount | ✅ PASS | host↔OWUI bidirectional | 0.2s |
| S15 | S15-04 | workspace helper imports | ✅ PASS | /Users/chris/AI_Output | 0.0s |
| S15 | S15-05 | AUDIO_STT_ENGINE disabled | ✅ PASS | empty (correct) | 0.1s |
| S16 | S16-01 | Security MCP health | ✅ PASS | service: security-mcp | 0.0s |
| S16 | S16-02 | classify_vulnerability (RCE — expect hig | ✅ PASS | {
| S16 | S16-03 | classify_vulnerability (info disclosure  | ✅ PASS | {
| S16 | S16-04 | classify_vulnerability returns probabili | ✅ PASS | {
| S21 | S21-01 | LLM router enabled | ✅ PASS | LLM_ROUTER_ENABLED=True | 0.0s |
| S21 | S21-02 | LLM router model available | ✅ PASS | model: hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterat | 0.0s |
| S21 | S21-03 | LLM router security intent | ✅ PASS | routed→auto-redteam \| model: qwen3-vl:32b | 61.7s |
| S21 | S21-03b | Model identity for auto-redteam | ⚠️  WARN | ROUTING MISMATCH: got qwen3-vl:32b, expected Ollama:baronllm  [UNCLASSIFIED] | 0.0s |
| S21 | S21-04 | LLM router coding intent | ✅ PASS | routed→auto-coding \| model: qwen3-coder:30b-a3b-q4_K_M | 21.3s |
| S21 | S21-05 | LLM router compliance intent | ✅ PASS | routed→auto-compliance \| model: granite4.1:8b | 10.5s |
| S21 | S21-06 | routing_descriptions.json | ✅ PASS | 17 workspace descriptions | 0.0s |
| S21 | S21-07 | routing_examples.json | ✅ PASS | 32 examples | 0.0s |
| S23 | S23-01 | GPT-OSS:20B available | ✅ PASS | gpt-oss in Ollama catalog: True | 0.0s |
| S23 | S23-03 | Gemma 4 E4B VLM available | ✅ PASS | gemma4:e4b in Ollama catalog: True | 0.0s |
| S23 | S23-04 | Phi-4 available | ✅ PASS | phi4:14b in Ollama catalog: True | 0.0s |
| S23 | S23-05 | Magistral-Small available | ✅ PASS | magistral in Ollama catalog: True | 0.0s |
| S23 | S23-06 | Phi-4-reasoning-plus available | ✅ PASS | phi4-reasoning in Ollama catalog: True | 0.0s |
| S23 | S23-07 | GLM-4.7-Flash available | ✅ PASS | glm-4.7-flash in Ollama catalog: True | 0.0s |
| S30 | S30-01 | ComfyUI direct | ℹ️  INFO | not running: All connection attempts failed | 0.0s |
| S30 | S30-02 | ComfyUI MCP bridge | ℹ️  INFO | HTTP 0 | 0.0s |
| S31 | S31-01 | Video MCP health | ℹ️  INFO | HTTP 0 | 0.0s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 808 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 3/5 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |
| S41 | S41-01 | /health/all aggregator | ✅ PASS | 9/14 services ok: pipeline, ollama, mcp_documents, mcp_execution, mcp_security | 0.1s |
| S41 | S41-02 | bench-* concurrency=1 | ✅ PASS | all 51 bench-* workspaces capped at 1 | 0.0s |
| S41 | S41-03 | /admin/refresh-tools | ✅ PASS | 34 tools registered | 0.0s |
| S41 | S41-04 | Power metrics in /metrics | ✅ PASS | portal5_power_* and portal5_energy_* present | 0.0s |
| S41 | S41-05 | Workspace consistency | ✅ PASS | 73 workspaces, pipe+yaml match | 0.0s |
| S42 | S42-01 | Browser MCP health | ✅ PASS | status=ok, profiles=0 | 0.0s |
| S42 | S42-02 | Browser MCP tools | ✅ PASS | 8 tools: browser_navigate, browser_snapshot, browser_click, browser_fill... | 0.0s |
| S50 | S50-01 | Empty prompt handled gracefully | ⚠️  WARN | unexpected HTTP 408  [UNCLASSIFIED] | 30.0s |
| S50 | S50-02 | Oversized prompt handled | ✅ PASS | HTTP 408 | 60.0s |
| S50 | S50-03 | Invalid model slug handled | ✅ PASS | HTTP 200 \| model=huihui_ai/Qwen3.6-abliterated: | 15.2s |
| S50 | S50-04 | Pipeline /health surfaces backend count | ✅ PASS | healthy: 6 | 0.0s |
| S50 | S50-05 | Malformed JSON rejected | ✅ PASS | HTTP 400 | 0.0s |
| S50 | S50-06 | Missing auth rejected with 401 | ✅ PASS | HTTP 401 | 0.0s |
| S60 | S60-01 | Tool registry loaded | ✅ PASS | 0 tools: ... | 0.0s |
| S60 | S60-02 | Workspace tool whitelists | ✅ PASS | 19/73 workspaces have tools | 0.0s |
| S60 | S60-03 | Persona tool resolution | ✅ PASS | tools_allow override works: ['execute_python'] | 0.0s |
| S60 | S60-04 | Tool dispatch function | ✅ PASS | exists | 0.0s |
| S60 | S60-05 | MAX_TOOL_HOPS | ✅ PASS | value=10 | 0.0s |
| S60 | S60-06 | Tool-call Prometheus metrics | ✅ PASS | portal5_tool_calls_total + duration present | 0.0s |
| S60 | S60-07 | agentorchestrator persona | ✅ PASS | slug=agentorchestrator, workspace=auto-agentic | 0.0s |
| S70 | S70-01 | SearXNG web search | ✅ PASS | 18 results returned | 3.0s |
| S70 | S70-02 | Research MCP health | ✅ PASS | {"status":"ok","service":"research-mcp","backend":"searxng"} | 0.0s |
| S70 | S70-03 | Memory MCP health | ✅ PASS | {"status":"ok","service":"memory-mcp","stored":6} | 0.0s |
| S70 | S70-04 | RAG MCP health | ✅ PASS | {"status":"ok","service":"rag-mcp","knowledge_bases":[]} | 0.0s |
| S70 | S70-05 | Embedding service health | ✅ PASS | {"status":"ok","model":"microsoft/harrier-oss-v1-0.6b"} | 0.0s |
| S70 | S70-06 | Research personas | ✅ PASS | 6/6 present | 0.0s |
| S70 | S70-07 | auto-research tool whitelist | ✅ PASS | tools: ['web_search', 'web_fetch', 'news_search', 'kb_search', 'kb_search_all',  | 0.0s |
| S70 | S70-08 | Memory MCP round-trip | ✅ PASS | stored+recalled: id=5a4b9c05, sim=0.42, 1 hits | 0.7s |
