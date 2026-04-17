# Portal 5 Acceptance Test Results — V6

**Date:** 2026-04-17 05:47:32
**Git SHA:** 10be523
**Sections:** S0, S1, S2, S12, S13, S40, S3a, S6, S10, S21, S3b, S11, S20, S22, S23, S4, S5, S8, S9, S7, S30, S31, S3
**Runtime:** 3088s (51m 28s)

## Summary

| Status | Count |
|--------|-------|
| ✅ PASS | 155 |
| ℹ️  INFO | 1 |
| **Total** | **156** |

## Results

| Section | ID | Name | Status | Detail | Duration |
|---------|-----|------|--------|--------|----------|
| S0 | S0-01 | Python version | ✅ PASS | Python 3.14.4 | 0.0s |
| S0 | S0-02 | Required packages | ✅ PASS | all present | 0.2s |
| S0 | S0-03 | .env file exists | ✅ PASS | /Users/chris/projects/portal-5/.env | 0.0s |
| S0 | S0-04 | PIPELINE_API_KEY configured | ✅ PASS | key length: 42 | 0.0s |
| S0 | S0-05 | Git repository | ✅ PASS | SHA: 10be523 | 0.0s |
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
| S2 | S2-01 | Docker daemon | ✅ PASS | Docker OK | 0.6s |
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
| S12 | S12-01 | SearXNG search | ✅ PASS | 32 results | 1.0s |
| S13 | S13-01 | Embedding service | ✅ PASS | HTTP 200 | 0.0s |
| S13 | S13-02 | Generate embedding | ✅ PASS | dim: 1024 | 0.4s |
| S40 | S40-01 | Pipeline /metrics | ✅ PASS | 906 metrics | 0.0s |
| S40 | S40-02 | Prometheus targets | ✅ PASS | 3/5 up | 0.0s |
| S40 | S40-03 | Grafana API | ✅ PASS | HTTP 401 | 0.0s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| model: mlx-community/Qwen3-Coder-Next-4bit | 52.9s |
| S3a | S3a-02 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| model: dolphin-llama3:8b | 6.5s |
| S3a | S3a-03 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum', 'loop'] \| model: dolphin-llama3:8b | 2.2s |
| S3a | S3a-04 | Workspace auto-security | ✅ PASS | signals: ['injection', 'XSS', 'authentication'] \| model: baronllm:q6_k | 17.0s |
| S3a | S3a-05 | Workspace auto-redteam | ✅ PASS | signals: ['sudo', 'privilege', 'root'] \| model: baronllm:q6_k | 8.4s |
| S3a | S3a-06 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| model: lily-cybersecurity:7b-q4_k_ | 9.4s |
| S3a | S3a-07 | Workspace auto-documents | ✅ PASS | signals: ['timeline', 'budget', 'section'] \| model: qwen3.5:9b | 17.9s |
| S6 | S6-01 | auto-security routing | ✅ PASS | signals: ['sql', 'inject', 'sanitize'] \| model: baronllm:q6_k | 8.5s |
| S6 | S6-02 | auto-redteam routing | ✅ PASS | signals: ['scan', 'pentest', 'OWASP'] \| model: baronllm:q6_k | 8.5s |
| S6 | S6-03 | auto-blueteam routing | ✅ PASS | signals: ['isolate', 'contain', 'incident'] \| model: lily-cybersecurity:7b-q4_k | 10.5s |
| S6 | S6-04 | Content-aware security routing | ✅ PASS | routed to security workspace: True | 8.6s |
| S10 | S10-01 | Persona bugdiscoverycodeassistant | ✅ PASS | signals: ['list', 'error'] | 5.7s |
| S10 | S10-02 | Persona codebasewikidocumentationskill | ✅ PASS | signals: ['param', 'Returns', 'str'] | 2.1s |
| S10 | S10-03 | Persona codereviewassistant | ✅ PASS | signals: ['list'] | 4.0s |
| S10 | S10-04 | Persona codereviewer | ✅ PASS | signals: ['==', 'bool', 'True'] | 4.1s |
| S10 | S10-05 | Persona devopsautomator | ✅ PASS | signals: ['#!/', 'bash', 'date'] | 5.1s |
| S10 | S10-06 | Persona devopsengineer | ✅ PASS | signals: ['pod', 'container', 'lifecycle'] | 5.6s |
| S10 | S10-07 | Persona ethereumdeveloper | ✅ PASS | signals: ['contract', 'pragma', 'solidity'] | 5.2s |
| S10 | S10-08 | Persona githubexpert | ✅ PASS | signals: ['rebase', 'merge', 'history'] | 4.8s |
| S10 | S10-09 | Persona javascriptconsole | ✅ PASS | signals: ['Math', 'PI', 'result'] | 0.9s |
| S10 | S10-10 | Persona kubernetesdockerrpglearningengin | ✅ PASS | signals: ['layer', 'image', 'cache'] | 4.9s |
| S10 | S10-11 | Persona linuxterminal | ✅ PASS | signals: ['du'] | 0.6s |
| S10 | S10-12 | Persona pythoncodegeneratorcleanoptimize | ✅ PASS | signals: ['sorted', 'key', 'dict'] | 2.8s |
| S10 | S10-13 | Persona pythoninterpreter | ✅ PASS | signals: ['[3, 2, 1]'] | 0.6s |
| S10 | S10-14 | Persona seniorfrontenddeveloper | ✅ PASS | signals: ['useState', 'useEffect', 'hook'] | 2.3s |
| S10 | S10-15 | Persona seniorsoftwareengineersoftwarear | ✅ PASS | signals: ['pattern', 'cache', 'load'] | 2.7s |
| S10 | S10-16 | Persona softwarequalityassurancetester | ✅ PASS | signals: ['test', 'case', 'valid'] | 5.5s |
| S10 | S10-17 | Persona sqlterminal | ✅ PASS | signals: ['role', 'admin'] | 1.9s |
| S10 | S10-18 | Persona dataanalyst | ✅ PASS | signals: ['correlation', 'causation', 'variable'] | 2.7s |
| S10 | S10-19 | Persona datascientist | ✅ PASS | signals: ['feature', 'transform', 'engineer'] | 5.5s |
| S10 | S10-20 | Persona excelsheet | ✅ PASS | signals: ['VLOOKUP', 'FALSE'] | 0.9s |
| S10 | S10-21 | Persona itarchitect | ✅ PASS | signals: ['redundant', 'failover', 'availability'] | 5.5s |
| S10 | S10-22 | Persona machinelearningengineer | ✅ PASS | signals: ['gradient', 'descent', 'learning'] | 2.2s |
| S10 | S10-23 | Persona researchanalyst | ✅ PASS | signals: ['search', 'inclusion', 'database'] | 5.5s |
| S10 | S10-24 | Persona statistician | ✅ PASS | signals: ['p-value', 'null', 'hypothesis'] | 5.5s |
| S10 | S10-25 | Persona creativewriter | ✅ PASS | signals: ['rain', 'detective', 'street'] | 2.2s |
| S10 | S10-26 | Persona itexpert | ✅ PASS | signals: ['bandwidth', 'network', 'gather'] | 2.7s |
| S10 | S10-27 | Persona techreviewer | ✅ PASS | signals: ['camera', 'chip', 'feature'] | 3.7s |
| S10 | S10-28 | Persona techwriter | ✅ PASS | signals: ['endpoint', 'request', 'response'] | 2.8s |
| S10 | S10-29 | Persona cybersecurityspecialist | ✅ PASS | signals: ['zero', 'trust', 'verify'] | 3.7s |
| S10 | S10-30 | Persona networkengineer | ✅ PASS | signals: ['vlan', 'switchport', 'interface'] | 1.6s |
| S10 | S10-31 | Persona redteamoperator | ✅ PASS | signals: ['T1566', 'phishing', 'exploit'] | 2.6s |
| S10 | S10-32 | Persona blueteamdefender | ✅ PASS | signals: ['ransom', 'detect', 'behavior'] | 5.5s |
| S10 | S10-33 | Persona pentester | ✅ PASS | signals: ['OWASP', 'test', 'methodology'] | 5.1s |
| S10 | S10-34 | Persona gptossanalyst | ✅ PASS | signals: ['trade', 'scale'] | 5.5s |
| S21 | S21-01 | LLM router enabled | ✅ PASS | LLM_ROUTER_ENABLED=True | 0.0s |
| S21 | S21-02 | LLM router model available | ✅ PASS | model: hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterat | 0.0s |
| S21 | S21-03 | LLM router security intent | ✅ PASS | HTTP 200 \| model: baronllm:q6_k | 2.7s |
| S21 | S21-04 | LLM router coding intent | ✅ PASS | HTTP 200 \| model: lmstudio-community/Devstral-Sm | 83.9s |
| S21 | S21-05 | LLM router compliance intent | ✅ PASS | HTTP 200 \| model: Jackrong/MLX-Qwen3.5-35B-A3B-C | 49.9s |
| S21 | S21-06 | routing_descriptions.json | ✅ PASS | 17 workspace descriptions | 0.0s |
| S21 | S21-07 | routing_examples.json | ✅ PASS | 30 examples | 0.0s |
| S3b | S3b-01 | Workspace auto-coding | ✅ PASS | MLX:True \| signals: ['def', 'return', 'reverse'] | 43.2s |
| S3b | S3b-02 | Workspace auto-agentic | ✅ PASS | MLX:True \| signals: ['service', 'domain'] | 53.5s |
| S3b | S3b-03 | Workspace auto-spl | ✅ PASS | MLX:True \| signals: ['index', 'source', 'fail'] | 78.7s |
| S3b | S3b-04 | Workspace auto-reasoning | ✅ PASS | MLX:True \| signals: ['150', 'distance', '60'] | 77.0s |
| S3b | S3b-05 | Workspace auto-research | ✅ PASS | MLX:True \| signals: ['qubit', 'quantum', 'compute'] | 59.8s |
| S3b | S3b-06 | Workspace auto-data | ✅ PASS | MLX:True \| signals: ['mean', 'deviation', 'standard'] | 85.4s |
| S3b | S3b-07 | Workspace auto-compliance | ✅ PASS | MLX:True \| signals: ['CIP', 'evidence', 'NERC'] | 50.4s |
| S3b | S3b-08 | Workspace auto-mistral | ✅ PASS | MLX:True \| signals: ['trade', 'scale', 'deploy'] | 69.9s |
| S3b | S3b-09 | Workspace auto-creative | ✅ PASS | MLX:True \| signals: ['think', 'learn'] | 34.1s |
| S3b | S3b-10 | Workspace auto-vision | ✅ PASS | MLX:True \| signals: ['text', 'contrast', 'color'] | 74.7s |
| S11 | S11-00 | MLX availability | ✅ PASS | state: ready |  |
| S11 | S11-01 | Persona fullstacksoftwaredeveloper (MLX) | ✅ PASS | MLX:True model=Devstral-Small-2507-MLX-4bit \| signals: ['GET', 'POST'] | 23.0s |
| S11 | S11-02 | Persona ux-uideveloper (MLX) | ✅ PASS | MLX:True model=Devstral-Small-2507-MLX-4bit \| signals: ['mobile', 'responsive'] | 22.1s |
| S11 | S11-03 | Persona splunksplgineer (MLX) | ✅ PASS | MLX:True model=Qwen3-Coder-30B-A3B-Instruct-8 \| signals: ['index', 'stats'] | 7.3s |
| S11 | S11-04 | Persona cippolicywriter (MLX) | ✅ PASS | MLX:True model=MLX-Qwen3.5-35B-A3B-Claude-4.6 \| signals: ['access', 'control'] | 15.8s |
| S11 | S11-05 | Persona nerccipcomplianceanalyst (MLX) | ✅ PASS | MLX:True model=MLX-Qwen3.5-35B-A3B-Claude-4.6 \| signals: ['CIP', 'patch'] | 13.5s |
| S11 | S11-06 | Persona gemmaresearchanalyst (MLX) | ✅ PASS | MLX:True model=gemma-4-31b-it-4bit \| signals: ['method', 'data'] | 33.2s |
| S11 | S11-07 | Persona gemma4e4bvision (MLX) | ✅ PASS | MLX:True model=MLX-Qwopus3.5-27B-v3-8bit \| signals: ['stack', 'trace'] | 75.7s |
| S11 | S11-08 | Persona gemma4jangvision (MLX) | ✅ PASS | MLX:True model=MLX-Qwopus3.5-27B-v3-8bit \| signals: ['credential', 'password'] | 83.6s |
| S11 | S11-09 | Persona phi4specialist (MLX) | ✅ PASS | MLX:True model=phi-4-8bit \| signals: ['spec', 'requirement'] | 26.0s |
| S11 | S11-10 | Persona magistralstrategist (MLX) | ✅ PASS | MLX:True model=Magistral-Small-2509-MLX-8bit \| signals: ['milestone', 'KPI'] | 82.1s |
| S11 | S11-11 | Persona phi4stemanalyst (MLX) | ✅ PASS | MLX:True model=DeepSeek-R1-Distill-Qwen-32B-M \| signals: ['pythagor', 'triangle | 117.6s |
| S20 | S20-01 | MLX proxy health | ✅ PASS | state: ready, data: {'active_server': 'lm', 'loaded_model': 'mlx-community/DeepS | 0.0s |
| S20 | S20-02 | MLX /v1/models | ✅ PASS | 23 models | 0.0s |
| S20 | S20-03 | MLX memory info | ✅ PASS | {'current': {'current': {'free_gb': 0.3, 'total_gb': 62.8, 'used_pct': 68, 'pres | 0.0s |
| S22 | S22-01 | MLX proxy for admission control | ✅ PASS | state: ready | 0.0s |
| S22 | S22-02 | MLX memory endpoint | ✅ PASS | available: 0.0GB | 0.0s |
| S22 | S22-03 | Admission control rejects oversized | ℹ️  INFO | proxy accepted 70B request (free RAM: 53.2GB >= 50GB threshold) — no rejection e | 8.0s |
| S22 | S22-04 | Model memory estimates | ✅ PASS | 17 models with size estimates | 0.0s |
| S23 | S23-01 | GPT-OSS:20B available | ✅ PASS | gpt-oss in models: True | 0.0s |
| S23 | S23-03 | Gemma 4 E4B VLM registered | ✅ PASS | gemma-4-E4B in MLX models: True | 0.0s |
| S23 | S23-04 | Phi-4 available | ✅ PASS | phi-4 in MLX models: True | 0.0s |
| S23 | S23-05 | Magistral-Small available | ✅ PASS | magistral in MLX models: True | 0.0s |
| S23 | S23-06 | Phi-4-reasoning-plus available | ✅ PASS | phi-4-reasoning-plus in MLX models: True | 0.0s |
| S4 | S4-01 | Documents MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S4 | S4-02 | Generate Word document | ✅ PASS | {
  "success": true,
  "path": "/app/data/generated/Test_Proposal_d3be463a.docx" | 0.1s |
| S4 | S4-03 | Generate Excel spreadsheet | ✅ PASS | {
  "success": true,
  "path": "/app/data/generated/Test_Budget_f189cbc7.xlsx",
 | 0.0s |
| S4 | S4-04 | Generate PowerPoint | ✅ PASS | {
  "success": true,
  "path": "/app/data/generated/Test_Presentation_ec29fc95.p | 0.0s |
| S5 | S5-01 | Sandbox MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S5 | S5-02 | Execute Python (sum 1-10) | ✅ PASS | {
  "success": true,
  "stdout": "55\n",
  "stderr": "",
  "exit_code": 0,
  "ti | 0.2s |
| S5 | S5-03 | Execute Python (list comprehension) | ✅ PASS | {
  "success": true,
  "stdout": "[0, 1, 4, 9, 16]\n",
  "stderr": "",
  "exit_c | 0.1s |
| S8 | S8-01 | MLX Speech health | ✅ PASS | voice_cloning: True | 0.0s |
| S8 | S8-02 | MLX Speech TTS | ✅ PASS | duration: 2.85s | 0.7s |
| S9 | S9-01 | MLX Speech ASR available | ✅ PASS | Qwen3-ASR | 0.0s |
| S7 | S7-01 | Music MCP health | ✅ PASS | service: music-mcp | 0.0s |
| S7 | S7-02 | Generate music (5s jazz) | ✅ PASS | {
  "success": true,
  "path": "/Users/chris/AI_Output/music_upbeat_jazz_piano_s | 60.6s |
| S30 | S30-01 | ComfyUI direct | ✅ PASS | version: 0.16.3 | 0.0s |
| S30 | S30-02 | ComfyUI MCP bridge | ✅ PASS | HTTP 200 | 0.0s |
| S31 | S31-01 | Video MCP health | ✅ PASS | HTTP 200 | 0.0s |
| S3a | S3a-01 | Workspace auto | ✅ PASS | signals: ['DNS', 'domain', 'IP'] \| model: mlx-community/Qwen3-Coder-Next-4bit | 112.0s |
| S3a | S3a-02 | Workspace auto-video | ✅ PASS | signals: ['sun', 'mountain', 'light'] \| model: dolphin-llama3:8b | 10.1s |
| S3a | S3a-03 | Workspace auto-music | ✅ PASS | signals: ['beat', 'drum', 'chill'] \| model: dolphin-llama3:8b | 3.0s |
| S3a | S3a-04 | Workspace auto-security | ✅ PASS | signals: ['injection', 'XSS', 'authentication'] \| model: baronllm:q6_k | 14.5s |
| S3a | S3a-05 | Workspace auto-redteam | ✅ PASS | signals: ['SUID', 'privilege', 'escalat'] \| model: baronllm:q6_k | 8.4s |
| S3a | S3a-06 | Workspace auto-blueteam | ✅ PASS | signals: ['traffic', 'network', 'monitor'] \| model: lily-cybersecurity:7b-q4_k_ | 9.2s |
| S3a | S3a-07 | Workspace auto-documents | ✅ PASS | signals: ['introduction', 'scope', 'timeline'] \| model: qwen3.5:9b | 17.9s |
| S3b | S3b-01 | Workspace auto-coding | ✅ PASS | MLX:True \| signals: ['def', 'return', 'reverse'] | 76.2s |
| S3b | S3b-02 | Workspace auto-agentic | ✅ PASS | MLX:False \| signals: ['service', 'API', 'decouple'] | 11.3s |
| S3b | S3b-03 | Workspace auto-spl | ✅ PASS | MLX:True \| signals: ['index', 'source', 'fail'] | 49.3s |
| S3b | S3b-04 | Workspace auto-reasoning | ✅ PASS | MLX:True \| signals: ['150', 'distance', '60'] | 78.1s |
| S3b | S3b-05 | Workspace auto-research | ✅ PASS | MLX:True \| signals: ['qubit', 'quantum', 'compute'] | 62.3s |
| S3b | S3b-06 | Workspace auto-data | ✅ PASS | MLX:False \| signals: ['mean', 'deviation', 'standard'] | 46.5s |
| S3b | S3b-07 | Workspace auto-compliance | ✅ PASS | MLX:False \| signals: ['evidence'] | 68.9s |
| S3b | S3b-08 | Workspace auto-mistral | ✅ PASS | MLX:True \| signals: ['trade', 'scale', 'deploy'] | 61.0s |
| S3b | S3b-09 | Workspace auto-creative | ✅ PASS | MLX:True \| signals: ['think', 'learn'] | 34.0s |
| S3b | S3b-10 | Workspace auto-vision | ✅ PASS | MLX:True \| signals: ['text', 'contrast', 'color'] | 78.8s |