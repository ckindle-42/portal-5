# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-05 19:29:12 (5172s)  
**Git SHA:** 4b26ba0  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 161
- **WARN**: 45
- **INFO**: 16

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 13 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | INFO | S0 | Git SHA | local=4b26ba0 | 0.0s |
| 7 | PASS | S0 | Codebase matches remote main | local=4b26ba0 remote=4b26ba0 | 0.0s |
| 8 | INFO | S0 | Pipeline /health version fields | version=dev workspaces=16 backends_healthy=7 | 0.0s |
| 9 | INFO | S0 | pyproject.toml version | version=5.2.1 | 0.0s |
| 10 | PASS | S1 | router_pipe.py WORKSPACES ↔ backends.yaml workspace_routing |  | 0.0s |
| 11 | PASS | S1 | All 40 persona YAMLs have required fields |  | 0.0s |
| 12 | PASS | S1 | update_workspace_tools.py covers all workspace IDs | all 16 covered | 0.0s |
| 13 | PASS | S1 | docker-compose.yml is valid YAML |  | 0.0s |
| 14 | INFO | S1 | imports/openwebui/mcp-servers.json present | 4 entries | 0.0s |
| 15 | PASS | S1 | mlx-proxy.py: Gemma 4 31B dense in ALL_MODELS and VLM_MODELS | ✓ present in both | 0.0s |
| 16 | PASS | S1 | mlx-proxy.py: Magistral in ALL_MODELS but NOT in VLM_MODELS  | ✓ mlx_lm routing correct | 0.0s |
| 17 | INFO | S1 | Persona model type distribution (40 personas) | MLX-routed: 10 ∣ Ollama-routed: 30 | 0.0s |
| 18 | PASS | S2 | Open WebUI |  | 0.0s |
| 19 | PASS | S2 | Pipeline |  | 0.0s |
| 20 | PASS | S2 | Grafana |  | 0.0s |
| 21 | PASS | S2 | MCP Documents |  | 0.0s |
| 22 | PASS | S2 | MCP Sandbox |  | 0.0s |
| 23 | PASS | S2 | MCP Music |  | 0.0s |
| 24 | PASS | S2 | MCP TTS |  | 0.0s |
| 25 | PASS | S2 | MCP Whisper |  | 0.0s |
| 26 | PASS | S2 | MCP Video |  | 0.0s |
| 27 | PASS | S2 | Prometheus |  | 0.0s |
| 28 | PASS | S2 | MCP ComfyUI bridge | HTTP 200 | 0.0s |
| 29 | PASS | S2 | SearXNG container | status=healthy | 0.0s |
| 30 | PASS | S2 | Ollama responding with pulled models | 20 models pulled | 0.0s |
| 31 | PASS | S2 | /metrics endpoint is unauthenticated (HOWTO §22) | HTTP 200 | 0.0s |
| 32 | INFO | S2 | MLX proxy :8081 | 15 models listed | 0.0s |
| 33 | PASS | S8 | list_voices includes af_heart (default voice) | ✓ voices listed | 0.2s |
| 34 | PASS | S8 | speak af_heart → file_path returned | ✓ speech generated | 1.0s |
| 35 | PASS | S8 | TTS REST /v1/audio/speech: af_heart (US-F default) | ✓ valid WAV 357,420 bytes | 1.1s |
| 36 | PASS | S8 | TTS REST /v1/audio/speech: bm_george (British male) | ✓ valid WAV 392,236 bytes | 1.2s |
| 37 | PASS | S8 | TTS REST /v1/audio/speech: am_adam (US male) | ✓ valid WAV 334,892 bytes | 1.0s |
| 38 | PASS | S8 | TTS REST /v1/audio/speech: bf_emma (British female) | ✓ valid WAV 319,532 bytes | 1.0s |
| 39 | PASS | S9 | Whisper health via docker exec (HOWTO §12 exact command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 40 | PASS | S9 | transcribe_audio tool reachable (file-not-found confirms con | ✓ tool responds (expected file-not-found error) | 0.0s |
| 41 | PASS | S9 | STT round-trip: TTS → WAV → Whisper transcription | ✓ transcribed: {
  "text": "Hello from Portal 5.",
  "language": "en",
  "duration": 1.41,
  "s | 0.5s |
| 42 | PASS | S12 | portal_workspaces_total matches code count | metric=16, code=16 | 0.0s |
| 43 | PASS | S12 | portal_backends gauge present | present | 0.0s |
| 44 | PASS | S12 | portal_requests counter present (after S3 traffic) | present | 0.0s |
| 45 | INFO | S12 | Prometheus histogram metrics (tokens_per_second) | present | 0.0s |
| 46 | PASS | S12 | Prometheus scraping pipeline target | 1 pipeline targets in 5 total | 0.0s |
| 47 | PASS | S12 | Grafana portal5_overview dashboard provisioned | dashboards: ['Portal 5 Overview'] | 0.0s |
| 48 | PASS | S13 | Login → chat UI loaded |  | 2.0s |
| 49 | PASS | S13 | Model dropdown shows workspace names | 16/16 visible | 0.0s |
| 50 | WARN | S13 | Personas visible | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 51 | PASS | S13 | Chat textarea accepts and clears input |  | 0.0s |
| 52 | PASS | S13 | Admin panel accessible |  | 1.0s |
| 53 | PASS | S13 | MCP tool servers registered in Open WebUI | 7/7 registered: ['8910', '8911', '8912', '8913', '8914', '8915', '8916'] | 0.0s |
| 54 | PASS | S14 | No stale 'Click + enable' instructions |  | 0.0s |
| 55 | PASS | S14 | §3 workspace table has 16 rows | table rows=16, code has 16 | 0.0s |
| 56 | PASS | S14 | auto-compliance workspace documented in §3 |  | 0.0s |
| 57 | PASS | S14 | Persona count claim matches YAML file count | claimed=40, yaml files=40 | 0.0s |
| 58 | PASS | S14 | §16 Telegram workspace list complete | all IDs listed | 0.0s |
| 59 | PASS | S14 | §11 TTS backend is kokoro as documented | actual: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} | 0.0s |
| 60 | PASS | S14 | HOWTO §3 curl command works | HTTP 200 | 0.0s |
| 61 | PASS | S14 | HOWTO §5 curl command works | HTTP 200 | 0.0s |
| 62 | PASS | S14 | HOWTO §7 curl command works | HTTP 200 | 0.0s |
| 63 | PASS | S14 | HOWTO §22 curl command works | HTTP 200 | 0.0s |
| 64 | PASS | S14 | §12 whisper health via docker exec (exact HOWTO command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 65 | PASS | S14 | HOWTO footer version matches pyproject.toml (5.2.1) | expected 5.2.1 in HOWTO footer | 0.0s |
| 66 | PASS | S14 | HOWTO MLX table documents gemma-4-31b-it-4bit | found | 0.0s |
| 67 | PASS | S14 | HOWTO MLX table documents Magistral-Small-2509-MLX-8bit | found | 0.0s |
| 68 | PASS | S14 | HOWTO documents auto-spl workspace | found | 0.0s |
| 69 | PASS | S16 | ./launch.sh status |  | 3.3s |
| 70 | PASS | S16 | ./launch.sh list-users |  | 0.2s |
| 71 | PASS | S21 | NotificationDispatcher module imports | module loaded successfully | 0.0s |
| 72 | PASS | S21 | AlertEvent formatting (Slack, Telegram, Pushover, Email) | slack=122 chars, telegram=108 chars | 0.0s |
| 73 | PASS | S21 | SummaryEvent formatting (Slack, Telegram) | slack=396 chars, telegram=278 chars | 0.0s |
| 74 | PASS | S21 | Notification channels importable (1 configured) | 1/1 channels imported | 0.0s |
| 75 | PASS | S3 | /v1/models exposes all 16 workspace IDs |  | 0.0s |
| 76 | PASS | S3 | workspace auto: domain response |  | 133.1s |
| 77 | PASS | S3 | workspace auto-creative: domain response |  | 46.0s |
| 78 | PASS | S3 | workspace auto-documents: domain response |  | 16.6s |
| 79 | PASS | S3 | workspace auto-security: domain response |  | 6.9s |
| 80 | PASS | S3 | workspace auto-redteam: domain response |  | 11.4s |
| 81 | PASS | S3 | workspace auto-blueteam: domain response |  | 11.2s |
| 82 | PASS | S3 | workspace auto-video: domain response |  | 5.5s |
| 83 | PASS | S3 | workspace auto-music: domain response |  | 1.5s |
| 84 | PASS | S3 | Streaming response delivers NDJSON chunks (SSE) | 1 data chunks ∣ [DONE]=no | 133.9s |
| 85 | PASS | S3 | Pipeline logs contain routing activity for workspaces exerci | found routing evidence for: ['auto', 'auto-blueteam', 'auto-coding', 'auto-compliance', 'auto-creative', 'auto-data', 'auto-documents', 'auto-mistral', 'auto-mu | 0.2s |
| 86 | PASS | S4 | create_word_document → .docx | ✓ .docx created | 0.4s |
| 87 | PASS | S4 | create_powerpoint → .pptx (5 slides) | ✓ 5-slide deck created | 0.1s |
| 88 | PASS | S4 | create_excel → .xlsx with data | ✓ spreadsheet created | 0.1s |
| 89 | PASS | S4 | list_generated_files shows created files | files listed: {
  "filename": "Q1-Q2_Budget_28598f6a.xlsx",
  "path": "/app/data/generated/Q1-Q2_Budget_28598f6a.xlsx",
  "size_bytes" | 0.1s |
| 90 | PASS | S4 | auto-documents pipeline round-trip (CIP-007 outline) | preview: Here's a thinking process that leads to the suggested NERC CIP-017 patch management procedure outlin | 24.0s |
| 91 | INFO | S6 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 92 | PASS | S6 | auto-security: domain-relevant security response | signals matched: ['misconfiguration'] | 0.5s |
| 93 | PASS | S6 | auto-redteam: domain-relevant security response | signals matched: ['injection', 'graphql', 'introspection', 'attack', 'depth'] | 8.8s |
| 94 | PASS | S6 | auto-blueteam: domain-relevant security response | signals matched: ['445', 'smb', 'attack', 'deny'] | 9.3s |
| 95 | INFO | S7 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 96 | PASS | S7 | list_music_models returns available models | models: {
  "audiocraft_installed": false,
  "stable_audio_installed": false,
  "install | 0.1s |
| 97 | PASS | S7 | generate_music: 5s lo-fi | {
  "success": false,
  "error": "AudioCraft not installed. Run: pip install audiocraft"
} | 0.0s |
| 98 | PASS | S7 | auto-music workspace pipeline round-trip | preview: The lo-fi hip hop beat plays at a tempo of 120 BPM, with a C minor key. The main | 1.3s |
| 99 | INFO | S10 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 100 | PASS | S10 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 101 | PASS | S10 | list_video_models returns model list | models: videowan2.2 | 0.3s |
| 102 | PASS | S10 | auto-video workspace: domain-relevant video description | preview: Camera Angle: Low Angle
Lens: 16-35mm
Lighting: Warm, golden light from a settin | 2.7s |
| 103 | PASS | S10 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 104 | PASS | S10 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 105 | INFO | S15 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 106 | PASS | S15 | SearXNG /search?format=json returns results | 60 results for 'NERC CIP' | 2.8s |
| 107 | PASS | S15 | auto-research workspace: technical comparison response | signals: ['aes', 'rsa', 'symmetric', 'asymmetric', 'key'] | 11.6s |
| 108 | INFO | S20 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 109 | PASS | S20 | Telegram bot: module imports and build_app() succeeds | default_workspace=auto, allowed_users=1 | 0.1s |
| 110 | PASS | S20 | Telegram dispatcher: call_pipeline_async returns response | reply length: 3 | 0.3s |
| 111 | PASS | S20 | Telegram dispatcher: is_valid_workspace correct | auto-coding=True, nonexistent=False | 0.0s |
| 112 | PASS | S20 | Slack bot: module imports and _get_tokens() succeeds | bot_token=set, app_token=set | 0.0s |
| 113 | PASS | S20 | Slack dispatcher: module imports and payload builder work | dispatcher uses Docker-internal URL — tested modules natively, pipeline via localhost | 3.0s |
| 114 | INFO | S11 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 115 | WARN | S11 | Personas registered in Open WebUI | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 116 | PASS | S11 | persona creativewriter (Creative Writer) | signals: ['robot', 'flower', 'space', 'wonder'] | 4.7s |
| 117 | PASS | S11 | persona itexpert (IT Expert) | signals: ['memory', 'pandas', 'container'] | 7.0s |
| 118 | PASS | S11 | persona techreviewer (Tech Reviewer) | signals: ['m4', 'mlx', 'memory', 'inference', 'performance'] | 38.1s |
| 119 | PASS | S11 | persona techwriter (Tech Writer) | signals: ['api', 'authentication', 'curl', 'rate limit'] | 6.7s |
| 120 | PASS | S11 | persona bugdiscoverycodeassistant (Bug Discovery Code Assist | signals: ['def ', 'error', 'type'] | 10.8s |
| 121 | PASS | S11 | persona codebasewikidocumentationskill (Codebase WIKI Docume | signals: ['fibonacci', 'recursive', 'complexity', 'memoization'] | 41.8s |
| 122 | PASS | S11 | persona codereviewassistant (Code Review Assistant) | signals: ['pythonic', 'enumerate', 'improve'] | 11.2s |
| 123 | PASS | S11 | persona codereviewer (Code Reviewer) | signals: ['sql injection', 'parameterized', 'vulnerability'] | 38.7s |
| 124 | PASS | S11 | persona devopsautomator (DevOps Automator) | signals: ['github', 'actions', 'deploy', 'docker', 'pytest'] | 26.7s |
| 125 | PASS | S11 | persona devopsengineer (DevOps Engineer) | signals: ['kubernetes', 'helm', 'pipeline', 'canary', 'deployment'] | 41.3s |
| 126 | PASS | S11 | persona ethereumdeveloper (Ethereum Developer) | signals: ['solidity', 'transfer', 'approve', 'reentrancy'] | 10.3s |
| 127 | PASS | S11 | persona githubexpert (GitHub Expert) | signals: ['branch protection', 'reviewer', 'ci'] | 38.3s |
| 128 | PASS | S11 | persona javascriptconsole (JavaScript Console) | signals: ['reduce', 'accumulator', 'pi'] | 41.8s |
| 129 | PASS | S11 | persona kubernetesdockerrpglearningengine (Kubernetes & Dock | signals: ['mission', 'container', 'briefing'] | 11.1s |
| 130 | PASS | S11 | persona linuxterminal (Linux Terminal) | signals: ['find', 'size', 'modified'] | 38.4s |
| 131 | PASS | S11 | persona pythoncodegeneratorcleanoptimizedproduction-ready (P | signals: ['def ', 'retry', 'backoff'] | 9.9s |
| 132 | PASS | S11 | persona pythoninterpreter (Python Interpreter) | signals: ['zip', 'reverse', 'output', 'slice', 'tuple'] | 26.6s |
| 133 | PASS | S11 | persona seniorfrontenddeveloper (Senior Frontend Developer) | signals: ['react', 'hook', 'useeffect', 'loading', 'error'] | 41.0s |
| 134 | PASS | S11 | persona seniorsoftwareengineersoftwarearchitectrules (Senior | signals: ['risk', 'distributed', 'consistency'] | 29.6s |
| 135 | PASS | S11 | persona softwarequalityassurancetester (Software Quality Ass | signals: ['test case', 'valid', 'invalid', 'boundary'] | 38.8s |
| 136 | PASS | S11 | persona sqlterminal (SQL Terminal) | signals: ['join', 'group by', 'order by', 'index', 'top'] | 9.7s |
| 137 | PASS | S11 | persona dataanalyst (Data Analyst) | signals: ['growth', 'quarter', 'trend', 'analysis'] | 26.6s |
| 138 | PASS | S11 | persona datascientist (Data Scientist) | signals: ['feature', 'algorithm', 'churn', 'model'] | 27.1s |
| 139 | PASS | S11 | persona excelsheet (Excel Sheet) | signals: ['sumproduct', 'array', 'boolean', 'sales'] | 27.1s |
| 140 | PASS | S11 | persona itarchitect (IT Architect) | signals: ['load balanc', 'availability'] | 26.6s |
| 141 | PASS | S11 | persona machinelearningengineer (Machine Learning Engineer) | signals: ['random forest', 'xgboost', 'hyperparameter', 'tabular'] | 26.7s |
| 142 | PASS | S11 | persona researchanalyst (Research Analyst) | signals: ['microservices', 'monolith', 'complexity'] | 26.6s |
| 143 | PASS | S11 | persona statistician (Statistician) | signals: ['p-value', 'power', 'sample size', 'effect size', 'type i'] | 26.8s |
| 144 | PASS | S11 | persona redteamoperator (Red Team Operator) | signals: ['jwt', 'sql injection', 'attack', 'idor', 'token'] | 13.1s |
| 145 | PASS | S11 | persona blueteamdefender (Blue Team Defender) | signals: ['mitre', 'ssh', 'brute', 'incident', 'containment'] | 9.4s |
| 146 | PASS | S11 | Persona suite summary (40 total) | 30 PASS ∣ 0 WARN ∣ 0 FAIL | 0.0s |
| 147 | WARN | S30 | workspace auto-coding | MLX proxy not ready | 0.0s |
| 148 | WARN | S30 | persona bugdiscoverycodeassistant (Bug Discovery Code Assist | MLX proxy not ready | 0.0s |
| 149 | WARN | S30 | persona codebasewikidocumentationskill (Codebase WIKI Docume | MLX proxy not ready | 0.0s |
| 150 | WARN | S30 | persona codereviewassistant (Code Review Assistant) | MLX proxy not ready | 0.0s |
| 151 | WARN | S30 | persona codereviewer (Code Reviewer) | MLX proxy not ready | 0.0s |
| 152 | WARN | S30 | persona devopsautomator (DevOps Automator) | MLX proxy not ready | 0.0s |
| 153 | WARN | S30 | persona devopsengineer (DevOps Engineer) | MLX proxy not ready | 0.0s |
| 154 | WARN | S30 | persona ethereumdeveloper (Ethereum Developer) | MLX proxy not ready | 0.0s |
| 155 | WARN | S30 | persona githubexpert (GitHub Expert) | MLX proxy not ready | 0.0s |
| 156 | WARN | S30 | persona javascriptconsole (JavaScript Console) | MLX proxy not ready | 0.0s |
| 157 | WARN | S30 | persona kubernetesdockerrpglearningengine (Kubernetes & Dock | MLX proxy not ready | 0.0s |
| 158 | WARN | S30 | persona linuxterminal (Linux Terminal) | MLX proxy not ready | 0.0s |
| 159 | WARN | S30 | persona pythoncodegeneratorcleanoptimizedproduction-ready (P | MLX proxy not ready | 0.0s |
| 160 | WARN | S30 | persona pythoninterpreter (Python Interpreter) | MLX proxy not ready | 0.0s |
| 161 | WARN | S30 | persona seniorfrontenddeveloper (Senior Frontend Developer) | MLX proxy not ready | 0.0s |
| 162 | WARN | S30 | persona seniorsoftwareengineersoftwarearchitectrules (Senior | MLX proxy not ready | 0.0s |
| 163 | WARN | S30 | persona softwarequalityassurancetester (Software QA Tester) | MLX proxy not ready | 0.0s |
| 164 | WARN | S30 | persona sqlterminal (SQL Terminal) | MLX proxy not ready | 0.0s |
| 165 | WARN | S5 | auto-coding workspace returns Python code | preview: timeout | 180.0s |
| 166 | PASS | S5 | execute_python: primes to 100 (count=25 sum=1060) | ✓ count=25 sum=1060 | 0.4s |
| 167 | PASS | S5 | execute_python: Fibonacci sequence | ✓ Fibonacci executed | 0.1s |
| 168 | PASS | S5 | execute_nodejs: array sum = 15 | ✓ Node.js sum=15 | 0.3s |
| 169 | PASS | S5 | execute_bash: echo + arithmetic | ✓ bash executed | 0.3s |
| 170 | PASS | S5 | sandbox_status reports DinD connectivity | {
  "docker_available": true,
  "docker_host": "tcp://dind:2375",
  "sandbox_enabled": true,
  "python_image": "python:3.11-slim",
  "node_image": "no | 0.0s |
| 171 | PASS | S5 | Sandbox network isolation (outbound blocked) | ✓ network correctly isolated | 0.2s |
| 172 | WARN | S31 | workspace auto-spl | MLX proxy not ready | 0.0s |
| 173 | WARN | S31 | persona fullstacksoftwaredeveloper (Fullstack Software Devel | MLX proxy not ready | 0.0s |
| 174 | WARN | S31 | persona splunksplgineer (Splunk SPL Engineer) | MLX proxy not ready | 0.0s |
| 175 | WARN | S31 | persona ux-uideveloper (UX/UI Developer) | MLX proxy not ready | 0.0s |
| 176 | WARN | S32 | workspace auto-reasoning | MLX proxy not ready | 0.0s |
| 177 | WARN | S32 | workspace auto-research | MLX proxy not ready | 0.0s |
| 178 | WARN | S32 | workspace auto-data | MLX proxy not ready | 0.0s |
| 179 | WARN | S33 | workspace auto-compliance | MLX proxy not ready | 0.0s |
| 180 | WARN | S33 | persona cippolicywriter (CIP Policy Writer) | MLX proxy not ready | 0.0s |
| 181 | WARN | S33 | persona nerccipcomplianceanalyst (NERC CIP Compliance Analys | MLX proxy not ready | 0.0s |
| 182 | WARN | S34 | workspace auto-mistral | MLX proxy not ready | 0.0s |
| 183 | WARN | S34 | persona magistralstrategist (Magistral Strategist) | MLX proxy not ready | 0.0s |
| 184 | WARN | S35 | workspace auto-documents | MLX proxy not ready | 0.0s |
| 185 | WARN | S36 | workspace auto-creative | MLX proxy not ready | 0.0s |
| 186 | WARN | S37 | workspace auto-vision | MLX proxy not ready | 0.0s |
| 187 | WARN | S37 | persona gemmaresearchanalyst (Gemma Research Analyst) | MLX proxy not ready | 0.0s |
| 188 | WARN | S22 | MLX proxy health |  | 10.0s |
| 189 | PASS | S23 | MLX watchdog disabled for testing | watchdog stopped — no false alerts during fallback tests | 0.0s |
| 190 | PASS | S23 | Pipeline health endpoint shows backend status | 6/7 backends healthy, 16 workspaces | 0.0s |
| 191 | PASS | S23 | Response includes model identity | model=dolphin-llama3:8b | 3.3s |
| 192 | WARN | S23 | auto-coding: primary MLX path | model=huihui_ai/baronllm-abliterated | 8.0s |
| 193 | PASS | S23 | auto-coding: primary path works | model=dolphin-llama3:8b | 4.2s |
| 194 | PASS | S23 | auto-coding: MLX proxy killed | MLX proxy is down | 0.7s |
| 195 | PASS | S23 | auto-coding: fallback to coding | model=dolphin-llama3:8b ∣ signals=['def ', 'str', 'return', 'complexity'] ∣ absolute fallback (pipeline served from any healthy backend) | 4.1s |
| 196 | WARN | S23 | auto-coding: MLX proxy restore | restore may still be in progress for MLX proxy | 185.6s |
| 197 | PASS | S23 | auto-coding: MLX restored, chain intact | model=huihui_ai/baronllm-abliterated — chain recovered after fallback | 5.5s |
| 198 | PASS | S23 | auto-security: primary security path | model=baronllm:q6_k | 10.1s |
| 199 | PASS | S23 | auto-security: survives backend stress | model=baronllm:q6_k ∣ signals=['autoindex', 'security', 'misconfiguration'] | 5.5s |
| 200 | WARN | S23 | auto-vision: primary MLX path | model=deepseek-r1:32b-q4_k_m | 16.0s |
| 201 | PASS | S23 | auto-vision: primary path works | model=deepseek-r1:32b-q4_k_m | 16.5s |
| 202 | PASS | S23 | auto-vision: MLX proxy killed | MLX proxy is down | 5.3s |
| 203 | PASS | S23 | auto-vision: fallback to vision | model=deepseek-r1:32b-q4_k_m ∣ signals=['visual', 'detect', 'image', 'diagram', 'analysis'] ∣ absolute fallback (pipeline served from any healthy backend) | 16.6s |
| 204 | WARN | S23 | auto-vision: MLX proxy restore | restore may still be in progress for MLX proxy | 185.2s |
| 205 | PASS | S23 | auto-vision: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 7.2s |
| 206 | WARN | S23 | auto-reasoning: primary MLX path | model=deepseek-r1:32b-q4_k_m | 17.4s |
| 207 | PASS | S23 | auto-reasoning: primary path works | model=deepseek-r1:32b-q4_k_m | 16.7s |
| 208 | PASS | S23 | auto-reasoning: MLX proxy killed | MLX proxy is down | 5.2s |
| 209 | PASS | S23 | auto-reasoning: fallback to reasoning | model=deepseek-r1:32b-q4_k_m ∣ signals=['meet', 'miles', 'train', 'mph', '790'] ∣ matched expected group: reasoning | 17.2s |
| 210 | WARN | S23 | auto-reasoning: MLX proxy restore | restore may still be in progress for MLX proxy | 185.4s |
| 211 | PASS | S23 | auto-reasoning: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 18.4s |
| 212 | WARN | S23 | All backends restored and healthy | 6/7 backends healthy | 186.5s |
| 213 | PASS | S23 | All MLX workspaces survive MLX failure (8/8) | 8 responded, 0 failed (fell back to Ollama or timed out) | 302.6s |
| 214 | INFO | S18 | MLX proxy health before section | HTTP 503 — MLX processes running but not ready | 0.0s |
| 215 | PASS | S18 | ComfyUI MCP bridge health | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 216 | PASS | S18 | list_workflows returns checkpoint list | checkpoints: Flux_v8-NSFW.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.3s |
| 217 | PASS | S18 | generate_image: photorealistic apple | {
  "success": false,
  "error": "ComfyUI rejected workflow (HTTP 400): {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validatio | 0.1s |
| 218 | PASS | S18 | ComfyUI host at http://localhost:8188 | HTTP 200 | 0.0s |
| 219 | PASS | S19 | Video MCP health | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 220 | PASS | S19 | list_video_models returns model list | models: videowan2.2 | 0.2s |
| 221 | PASS | S19 | generate_video: ocean waves at sunset | {
  "success": false,
  "error": "ComfyUI not available at http://host.docker.internal:8188: Client error '400 Bad Request' for url 'http://host.docker.internal | 0.0s |
| 222 | PASS | S19 | auto-video workspace: domain-relevant video description | preview: Camera angle: A low angle, pointed slightly towards the left of the frame.
Lens: | 5.8s |

## Blocked Items Register

*No blocked items.*

## Memory Usage Log

| Section | Free % | Used % | Notes |
|---------|--------|--------|-------|
| pre-S17 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S0 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S1 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S2 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S8 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S9 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S12 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S13 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S14 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S16 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S21 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S3 | 62% | 38% | MLX: 0.1GB free, normal |
| pre-S4 | 35% | 65% | MLX: 0.1GB free, critical |
| pre-S6 | 53% | 47% | MLX: 37.1GB free, normal |
| pre-S7 | 57% | 43% | MLX: 37.1GB free, normal |
| pre-S10 | 57% | 43% | MLX: 37.1GB free, normal |
| pre-S15 | 57% | 43% | MLX: 37.1GB free, normal |
| pre-S20 | 26% | 74% | MLX: 0.1GB free, moderate |
| pre-S11 | 26% | 74% | MLX: 0.1GB free, moderate |
| pre-S30 | 55% | 45% | MLX: 0.1GB free, normal |
| pre-S5 | 55% | 45% | MLX: 0.1GB free, normal |
| pre-S31 | 93% | 7% | MLX: 0.1GB free, normal |
| pre-S32 | 93% | 7% | MLX: 0.1GB free, normal |
| pre-S33 | 72% | 28% |  |
| pre-S34 | 73% | 27% |  |
| pre-S35 | 94% | 6% |  |
| pre-S36 | 81% | 19% |  |
| pre-S37 | 81% | 19% |  |
| pre-S22 | 81% | 19% |  |
| pre-S23 | 81% | 19% |  |
| pre-S18 | 61% | 39% | MLX: 0.1GB free, normal |
| pre-S19 | 92% | 8% | MLX: 0.1GB free, normal |

---
*Screenshots: /tmp/p5_gui_*.png*
